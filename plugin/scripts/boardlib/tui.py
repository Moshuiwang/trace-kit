# -*- coding: utf-8 -*-
"""tmux TUI 主循环（接口约定 §8）。归属：S-3。

出处：trace-kit #12 v2 第 7 / 8 / 9 条（动效、交互、差异重画）；https://github.com/Moshuiwang/lingxi/issues/580（键盘逐序列分发）；
https://github.com/Moshuiwang/lingxi/issues/589 顺带两条隐患（刷新线程 finally 清理＋看门狗；整轮超时）；账本 R2-1 / R2-2 / R2-4 / R2-5 / R2-7。

    run(args, build, source=None) -> int
        args：board.py 的参数对象（view / width / height / interval / timeout / no_anim / repo_root / trace / fixture）。
        build()：返回 Board；在后台线程调用，可能很慢。source：采集源，若有 `cancel()`（退而求其次 `kill_all()`）供看门狗取消旧轮。
        - 每轮刷新一个线程；线程 `finally` 必清句柄，结果只在轮次号仍有效时写回（迟到结果丢弃）；结果未被主循环消费前不起新轮。
        - 看门狗：超过 args.timeout + WATCHDOG_GRACE 秒未返回视为本轮失败——保留上一帧、头部告警「刷新超时」，调用 `source.cancel()`
          杀本轮子进程，有界等旧线程退出；旧线程没退出就显示「上一轮未结束」且不起新轮，退出后下一轮（定时 / r / 任务表变化）照常起线程。
          线程异常同样只告警不停刷。
        - 终端会话上下文（Terminal）：进入＝备用屏 / 隐藏光标 / bracketed paste / cbreak＋IXON 关；退出＝tcflow(TCOON) → SGR 复位 /
          粘贴关 / 光标 / 主屏 → termios（TCSANOW）→ 信号，各步独立 best-effort。SIGTERM / SIGHUP 受控退出（128＋信号号）；
          SIGTSTP 先恢复终端再挂起，SIGCONT 后重进并整屏重画；SIGWINCH 重排。
        - 差异重画：只重写与上一帧不同的行；动效 0.18 s 一格只写动效格；select 等待受键盘半序列期限（keys.wait_hint）约束。
        - 键：v 切视图、r 立即刷新、a 动效开关、q / Ctrl-C 退出、↑↓ / PageUp / PageDown / Home / End 滚动；PASTE / ESC 忽略。
        - 任务表文件 mtime 变化即时刷新；--interval 定时刷新。
"""
from __future__ import annotations

import dataclasses
import os
import re
import select
import signal
import sys
import termios
import threading
import time
from datetime import datetime, timezone

from . import render
from .keys import KeyParser
from .model import Board, Header

TICK = 0.18              # 动效一格
IDLE_WAIT = 1.0          # 无动效时 select 最长等待
WATCHDOG_GRACE = 5.0     # 看门狗宽限：采集层自己的整轮超时 == args.timeout，先让它有机会带着部分结果返回
JOIN_GRACE = 0.5         # 看门狗取消旧轮后在主循环里最多等它退出的秒数
ENTER_SEQ = "\x1b[?1049h\x1b[?25l\x1b[?2004h\x1b[2J"
LEAVE_SEQ = "\x1b[0m\x1b[?2004l\x1b[?25h\x1b[?1049l"


class _Stop(Exception):
    """受控退出（SIGTERM / SIGHUP）：带退出码从主循环抛出，与 q 走同一个 finally。"""

    def __init__(self, code: int):
        super().__init__(code)
        self.code = code


class Terminal:
    """终端会话上下文（账本 R2-1 / R2-2）：进入 / 退出的每一步各自独立 best-effort，任一步失败不影响其余步。"""

    def __init__(self, fd, out):
        self.fd, self.out = fd, out
        try:
            self.out_fd = out.fileno()
        except (OSError, ValueError, AttributeError):
            self.out_fd = None
        self.saved = None
        self.active = False

    def _emit(self, seq: str) -> None:
        """进出序列直接写 fd：信号处理器可能在 sys.stdout 一次大写入的中途被调用，经缓冲对象会重入报错。"""
        try:
            self.out.flush()
        except (RuntimeError, OSError, ValueError):
            pass
        try:
            if self.out_fd is not None:
                os.write(self.out_fd, seq.encode("utf-8"))
            else:
                self.out.write(seq)
                self.out.flush()
        except (RuntimeError, OSError, ValueError):
            pass

    def enter(self) -> None:
        try:
            if self.saved is None:
                self.saved = termios.tcgetattr(self.fd)
            attrs = termios.tcgetattr(self.fd)
            attrs[0] &= ~(termios.IXON | termios.IXOFF)        # Ctrl-S / Ctrl-Q 不冻结 pane，当普通按键
            attrs[3] &= ~(termios.ICANON | termios.ECHO)       # cbreak；保留 ISIG（Ctrl-C → KeyboardInterrupt）
            attrs[6][termios.VMIN], attrs[6][termios.VTIME] = 1, 0
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
        except (termios.error, OSError, ValueError):
            pass
        self._emit(ENTER_SEQ)
        self.active = True

    def leave(self) -> None:
        self.active = False
        try:
            termios.tcflow(self.fd, termios.TCOON)             # 先解除可能的输出流控，否则后面的写会永远等 Ctrl-Q
        except (termios.error, OSError, ValueError):
            pass
        self._emit(LEAVE_SEQ)
        try:
            if self.saved is not None:
                termios.tcsetattr(self.fd, termios.TCSANOW, self.saved)   # TCSANOW：不等输出排空
        except (termios.error, OSError, ValueError):
            pass


class Refresher:
    """后台刷新状态机：同一时刻至多一个有效轮次；结果未消费不起新轮；看门狗取消旧轮并有界等待。"""

    def __init__(self, build, timeout, cancel=None):
        self.build, self.timeout, self.cancel = build, float(timeout), cancel
        self.lock = threading.Lock()
        self.gen = 0
        self.thread = None
        self.started = None
        self.result = None
        self.stale = None            # 看门狗放手但仍活着的旧线程
        self.stale_since = None

    def busy(self) -> bool:
        with self.lock:
            return self.thread is not None

    def blocked(self) -> bool:
        """旧轮（已作废）还没退出：此时不起新轮（账本 R2-5）。"""
        with self.lock:
            if self.stale is not None and not self.stale.is_alive():
                self.stale, self.stale_since = None, None
            return self.stale is not None

    def blocked_for(self) -> float:
        with self.lock:
            return (time.monotonic() - self.stale_since) if self.stale_since is not None else 0.0

    def elapsed(self) -> float:
        with self.lock:
            return (time.monotonic() - self.started) if (self.thread is not None and self.started is not None) else 0.0

    def start(self) -> bool:
        """起一轮；已有轮次在跑、结果尚未被 poll 取走（账本 R2-4）、旧轮未结束（账本 R2-5）都返回 False。"""
        with self.lock:
            if self.thread is not None or self.result is not None:
                return False
            if self.stale is not None:
                if self.stale.is_alive():
                    return False
                self.stale, self.stale_since = None, None
            self.gen += 1
            gen = self.gen
            self.result, self.started = None, time.monotonic()
            t = threading.Thread(target=self._work, args=(gen,), name="board-refresh-%d" % gen, daemon=True)
            self.thread = t
        t.start()
        return True

    def _work(self, gen):
        outcome = ("error", "线程未返回结果")
        try:
            board = self.build()
            board.validate()
            outcome = ("ok", board)
        except BaseException as exc:  # noqa: BLE001 —— 线程里任何异常都要回到主循环，不静默
            outcome = ("error", "%s: %s" % (type(exc).__name__, exc))
        finally:
            with self.lock:
                if gen == self.gen:          # 迟到（已被看门狗作废）的轮次不写回
                    self.result = outcome
                    self.thread = None

    def poll(self):
        """取本轮结果：("ok", board) / ("error", text) / ("timeout", text)；无事 None。"""
        old, el = None, 0.0
        with self.lock:
            if self.result is not None:
                r, self.result = self.result, None
                return r
            if self.thread is not None and self.started is not None:
                el = time.monotonic() - self.started
                if el > self.timeout + WATCHDOG_GRACE:
                    self.gen += 1            # 作废本轮：线程 finally 时发现轮次号不符，结果丢弃
                    old, self.thread = self.thread, None
        if old is None:
            return None
        if self.cancel is not None:          # 杀本轮子进程（LiveSource.cancel / kill_all）
            try:
                self.cancel()
            except Exception:  # noqa: BLE001 —— 取消失败也不能让主循环死
                pass
        old.join(JOIN_GRACE)
        text = "%.0f 秒未返回" % el
        if old.is_alive():
            with self.lock:
                self.stale, self.stale_since = old, time.monotonic()
            text += "；上一轮未结束，等它退出后再起新轮"
        return ("timeout", text)


def _tasktable_path(args):
    """要盯 mtime 的任务表：夹具目录直接取；否则 docs/traces/ 下 --trace 指定或编号最大的目录。"""
    fx = getattr(args, "fixture", None)
    if fx:
        return os.path.join(fx, "任务表.md")
    base = os.path.join(getattr(args, "repo_root", ".") or ".", "docs", "traces")
    try:
        names = os.listdir(base)
    except OSError:
        return None
    want, best = getattr(args, "trace", None), None
    for n in names:
        m = re.match(r"(\d+)-", n)
        if not m:
            continue
        num = int(m.group(1))
        if want is not None and num != want:
            continue
        if best is None or num > best[0]:
            best = (num, n)
    return os.path.join(base, best[1], "任务表.md") if best else None


def _mtime(path):
    if not path:
        return None
    try:
        return os.stat(path).st_mtime_ns
    except OSError:
        return None


def placeholder_board(now=None) -> Board:
    """还没有任何一轮成功时的占位帧。"""
    h = Header("采集中…", "", "", "", [], "", "", [], [])
    return Board(h, [], [], now or datetime.now(timezone.utc))


def with_warnings(board, warnings):
    """把 TUI 侧告警（刷新超时 / 刷新异常）叠到头部，不改动原 board。"""
    if board is None:
        board = placeholder_board()
    if not warnings:
        return board
    header = dataclasses.replace(board.header, warnings=list(board.header.warnings) + list(warnings))
    return dataclasses.replace(board, header=header)


def _redraw(out, lines, prev):
    parts = ["\x1b[%d;1H%s\x1b[K" % (i + 1, ln) for i, ln in enumerate(lines) if i >= len(prev) or prev[i] != ln]
    for i in range(len(lines), len(prev)):
        parts.append("\x1b[%d;1H\x1b[K" % (i + 1))
    if parts:
        out.write("".join(parts))
        out.flush()


def _tick(out, anim, phase):
    parts = []
    for border, col, num in anim:
        n = len(border)
        for k, (x, y, ch) in enumerate(border):
            hot = n and ((k - phase) % n) in (0, 1, 2, 3)
            parts.append("\x1b[%d;%dH\x1b[38;5;%dm%s%s\x1b[0m" % (y + 1, x + 1, render.BRIGHT if hot else col, "\x1b[1m" if hot else "", ch))
        for (x, y, ch) in num:
            parts.append("\x1b[%d;%dH\x1b[38;5;%dm%s\x1b[0m" % (y + 1, x + 1, render.BRIGHT if (phase // 2) % 2 == 0 else render.DIM, ch))
    if parts:
        out.write("".join(parts))
        out.flush()


def run(args, build, source=None) -> int:
    fd = sys.stdin.fileno()
    out = sys.stdout
    if not (os.isatty(fd) and out.isatty()):
        sys.stderr.write("board.py：TUI 需要终端（stdin / stdout 都是 tty）；纯文本请用 --dump\n")
        return 2
    W = int(getattr(args, "width", None) or 150)
    H = int(getattr(args, "height", None) or 52)
    view = getattr(args, "view", "simple") if getattr(args, "view", "simple") in render.VIEW_LABEL else "simple"
    animate = not getattr(args, "no_anim", False)
    interval = max(1, int(getattr(args, "interval", 300) or 300))
    timeout = max(1, int(getattr(args, "timeout", 60) or 60))
    tt_path = _tasktable_path(args)
    tt_mtime = _mtime(tt_path)
    cancel = getattr(source, "cancel", None) or getattr(source, "kill_all", None)
    parser, ref = KeyParser(), Refresher(build, timeout, cancel)
    term = Terminal(fd, out)
    board, warnings = None, []
    scroll, phase, prev_lines, anim, avail = 0, (1 if animate else 0), [], [], 1
    dirty, pending, resized, resumed = True, False, [False], [False]

    def on_winch(*_):
        resized[0] = True

    def on_stop(signum, _frame):
        raise _Stop(128 + signum)

    def on_tstp(*_):                                       # 账本 R2-1：挂起前恢复终端，再真的停下
        term.leave()
        signal.signal(signal.SIGTSTP, signal.SIG_DFL)
        os.kill(os.getpid(), signal.SIGTSTP)

    def on_cont(*_):                                       # 恢复后重进 TUI 模式，主循环整屏重画
        signal.signal(signal.SIGTSTP, on_tstp)
        term.enter()
        resumed[0] = True

    saved_handlers = {}
    for sig, handler in ((signal.SIGWINCH, on_winch), (signal.SIGTERM, on_stop), (signal.SIGHUP, on_stop),
                         (signal.SIGTSTP, on_tstp), (signal.SIGCONT, on_cont)):
        try:
            saved_handlers[sig] = signal.signal(sig, handler)
        except (ValueError, OSError):
            pass
    code = 0
    try:
        term.enter()
        ref.start()
        last_start = time.monotonic()
        note_at = 0.0
        while True:
            res = ref.poll()
            if res is not None:
                kind, payload = res
                if kind == "ok":
                    board, warnings = payload, []
                elif kind == "error":
                    warnings = ["刷新异常：" + payload]
                else:
                    warnings = ["刷新超时（%s）" % payload]
                dirty = True
            now = time.monotonic()
            m = _mtime(tt_path)
            if m != tt_mtime:
                tt_mtime, pending = m, True
            if now - last_start >= interval:
                pending = True
            if pending and ref.start():
                pending, last_start, dirty = False, now, True
            if resumed[0]:
                resumed[0] = False
                prev_lines, dirty = [], True
            if resized[0]:
                resized[0] = False
                try:
                    sz = os.get_terminal_size(out.fileno())
                    W, H = sz.columns, sz.lines
                except OSError:
                    pass
                prev_lines, dirty = [], True
                out.write("\x1b[2J")
            if (ref.busy() or ref.blocked()) and now - note_at >= 1.0:
                note_at, dirty = now, True          # 「刷新中 Ns」/「上一轮未结束 Ns」每秒更新一次
            if dirty:
                shown = with_warnings(board, warnings)
                limit = render.scroll_limit(shown, view, W, H)
                scroll = max(0, min(scroll, limit))
                if ref.busy():
                    note = "刷新中 %ds" % ref.elapsed()
                elif ref.blocked():
                    note = "上一轮未结束 %ds" % ref.blocked_for()
                else:
                    note = ""
                lines, anim, avail = render.frame(shown, view, W, H, scroll, phase if animate else 0, note=note)
                _redraw(out, lines, prev_lines)
                prev_lines, dirty = lines, False
            if animate and anim:
                _tick(out, anim, phase)
                phase += 1
            wait = TICK if (animate and anim) else IDLE_WAIT
            hint = parser.wait_hint()
            if hint is not None:                             # 账本 R2-7：半序列期限由解析器定，不随动画 tick
                wait = min(wait, max(0.01, hint))
            r, _, _ = select.select([fd], [], [], wait)
            if not r:
                parser.flush()                               # 只在过期后才把孤立 Esc / 半序列清出
                continue
            try:
                data = os.read(fd, 4096)
            except OSError:
                data = b""
            if not data:
                return 0                                     # 终端关闭
            for key in parser.feed(data):
                if key in ("q", "Q", "CTRL_C"):
                    return 0
                if key in ("v", "V"):
                    view = "complex" if view == "simple" else "simple"
                    scroll, dirty = 0, True
                elif key in ("r", "R"):
                    pending, dirty = True, True
                elif key in ("a", "A"):
                    animate = not animate
                    phase = 1 if animate else 0
                    prev_lines, dirty = [], True             # 整屏重画，抹掉残留的高亮格
                elif key == "DOWN":
                    scroll, dirty = scroll + 1, True
                elif key == "UP":
                    scroll, dirty = max(0, scroll - 1), True
                elif key == "PGDN":
                    scroll, dirty = scroll + max(1, avail - 2), True
                elif key == "PGUP":
                    scroll, dirty = max(0, scroll - max(1, avail - 2)), True
                elif key == "HOME":
                    scroll, dirty = 0, True
                elif key == "END":
                    scroll, dirty = 10 ** 9, True
                # PASTE / ESC / 其他按键：忽略
    except KeyboardInterrupt:
        code = 0
    except _Stop as exc:
        code = exc.code
    finally:
        term.leave()
        for sig, handler in saved_handlers.items():
            try:
                signal.signal(sig, handler)
            except (ValueError, OSError, TypeError):
                pass
    return code

#!/usr/bin/env bash
# 套件项目中立守卫（v0.8.0 前名 check_no_lingxi.sh）：方法正文 METHOD.md、插件 plugin/、骨架 template/
# 不得带任何一个采用项目的私货——产品名词、业务名词、主机名、本机路径、凭据形态；
# 只允许出现在「出处」行里的采用项目 GitHub 链接与 examples/lingxi/ 路径引用。examples/ 不在名词扫描范围（G3 档本就是项目特有）。
# 私有采用项目的名词表不进公开仓库：从本机不入库文件读取（每行一条扩展正则，# 开头为注释，按不区分大小写匹配），
# 路径取 TRACE_KIT_PRIVATE_TERMS_FILE，缺省为 ${XDG_CONFIG_HOME:-$HOME/.config}/trace-kit/private-terms.txt；读不到只跑公开表并明示。
# 出处：Trace #1 合同 §2「显式除外」与分级清单 E 节（铁律 1 / 2）；方法正文迁入本仓后扩为项目中立（CHANGELOG v0.8.0）。
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
git rev-parse --git-dir >/dev/null 2>&1 || { printf '不在 git 仓库里：全仓扫描无法进行，拒绝判绿。\n' >&2; exit 2; }

# 公开名词表（main 上既有，已公开）。
pattern='lingxi|LINGXI|灵犀|飞书|Bot-Test|Bot-Prod|百炼|MCP|Agent SDK|银河|花名册|JumpServer|Supabase|biai|biplus|/home/[^/ ]+/|E-021|oc_[a-z0-9]{6}|cli_[a-z0-9]{6}|ou_[a-z0-9]{6}|ghs_[A-Za-z0-9]|ghp_[A-Za-z0-9]|gho_[A-Za-z0-9]'
# 出处链接放行（整行放行；「先剥链接再匹配」为下版候选，见修订 Issue）。
allow='github\.com/Moshuiwang/lingxi|github\.com/startimes-bi/|examples/lingxi/'
targets=(METHOD.md template plugin .claude-plugin)
hits=$(grep -rnIE "${pattern}" "${targets[@]}" 2>/dev/null | grep -vE "${allow}" || true)
if [[ -n "${hits}" ]]; then
  printf '项目名词命中（%s 只允许在「出处」行引用采用项目的 GitHub 链接）：\n%s\n' "${targets[*]}" "${hits}" >&2
  exit 1
fi

# 全仓（含 docs/traces、examples、CHANGELOG，含未跟踪文件）都不得出现本机 / 主机 / 凭据形态；本文件与 refill_diff.sh 的关键词表除外。
machine_pattern='/home/[^/ ]+/|TZ-server|biai-|biplus|oc_[a-z0-9]{6}|cli_[a-z0-9]{6}|ou_[a-z0-9]{6}|ghs_[A-Za-z0-9]|ghp_[A-Za-z0-9]|gho_[A-Za-z0-9]'
machine_hits=$(git grep --untracked -nIE "${machine_pattern}" -- . ':!scripts/kit/check_project_neutral.sh' ':!scripts/kit/refill_diff.sh' || true)
if [[ -n "${machine_hits}" ]]; then
  printf '全仓不得出现本机路径 / 主机名 / 凭据形态：\n%s\n' "${machine_hits}" >&2
  exit 1
fi

# 私有采用项目名词：全仓不得出现（出处链接行除外）。既有命中暂列豁免（v0.8.0 引入时已存在；是否清理待产品负责人决定，未决前不删改）。
private_file="${TRACE_KIT_PRIVATE_TERMS_FILE:-${XDG_CONFIG_HOME:-${HOME}/.config}/trace-kit/private-terms.txt}"
private_exempt=(
  ':!docs/traces/1-trace-kit-v0.1.0/自回灌报告-附录.txt'
)
if [[ -r "${private_file}" ]]; then
  private_pattern=$(grep -vE '^[[:space:]]*(#|$)' "${private_file}" | paste -sd '|' - || true)
  if [[ -n "${private_pattern}" ]]; then
    private_hits=$(git grep --untracked -niIE "${private_pattern}" -- . "${private_exempt[@]}" | grep -vE "${allow}" || true)
    if [[ -n "${private_hits}" ]]; then
      printf '全仓不得出现私有采用项目的名词 / 业务事实（公开仓库只写方法层面的结论）：\n%s\n' "${private_hits}" >&2
      exit 1
    fi
    private_note="私有名词表已加载"
  else
    private_note="私有名词表为空"
  fi
else
  private_note="私有名词表未加载（本机无 ${private_file##*/}，只跑公开表）"
fi
printf '项目中立守卫：通过（%s；全仓机器事实零命中；%s）\n' "${targets[*]}" "${private_note}"

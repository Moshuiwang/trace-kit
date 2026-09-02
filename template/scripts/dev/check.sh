#!/usr/bin/env bash
# 一键复现门禁环境 + 本机分层验证。
# 出处：lingxi https://github.com/Moshuiwang/lingxi/issues/236（PR #233 漂移事故：本机多装了门禁没装的包，
# 同一棵树本机全绿、CI 直接 ERROR）；验证：5 个批次收口前「本机 full 绿」。
#
# 用法：
#   scripts/dev/check.sh                    # 按当前改动自动分层（对比 --base，默认 main）
#   scripts/dev/check.sh docs|fast|full     # 强制指定层级，跳过自动判定
#   scripts/dev/check.sh --base <ref>        # 指定分层对比基线
#   scripts/dev/check.sh --committed-only    # 分层判定只看已提交差异，不含工作树改动
#   scripts/dev/check.sh --print-mode        # 只打印分层结论，不安装依赖、不运行任何检查
#   scripts/dev/check.sh --reuse-venv        # 复用已存在的虚拟环境，跳过默认的重建
#
# 三层与 CI 的对应关系（「验证与门禁」文档的「CI 分层」与「本机与 CI 同构」两节）：
#   docs  等价于 Story / docs 与 Epic Full / docs：只跑 scripts/ci/verify_docs.sh，
#         不装依赖、不起数据库或 Docker。
#   fast  等价于 Story / code fast：extras 与 Python 版本现读自 .github/workflows/story.yml，
#         干净虚拟环境里跑 scripts/ci/verify_repository.sh；不构建镜像。
#   full  等价于 Epic Full / gate **这一个作业**（不是整个 Epic Full）：extras 与 Python 版本
#         现读自 .github/workflows/ci.yml，干净虚拟环境重建后跑 verify_repository.sh。
#         本骨架没有数据库，fast 与 full 的差别只在配方来源；两者都不含 Epic Full / image 的
#         镜像构建与 compose 结构核对——那些仍只在 CI 里跑。
#
# **extras 与 Python 版本不在本脚本里硬编码**：全部由 scripts/dev/gate_spec.py 从上述两份
# 工作流 YAML 现读。不允许「本机一份、门禁一份」两处清单迟早漂移。工作流改了这些值，本脚本
# 下一次运行就自动跟着变；工作流的写法本身变了导致解析不出来，gate_spec.py 会响亮失败并说明
# 原因，不会安静地退回旧值。gate_spec.py 的输出只按 KEY=value 逐行解析，**不使用 eval**——
# 工作流 YAML 里的取值来自检出的分支内容，不受信任，eval 会把其中的 `$(...)` 当命令执行
# （上游独立审查实测：把一个取值改成 `x$(id>/tmp/PWNED)`，eval 真的执行了它）。
#
# **虚拟环境默认每次重建，不做「存在即复用」的缓存**：本机装了门禁不装的包（无论是手工调试
# 时装的、旧配方残留的、还是上游传递依赖变化带进来的）如果被静默复用，这个工具就会给出它
# 本该消灭的那种假信心。需要跳过重建加速反复调用时用 `--reuse-venv` 显式选择，默认不这样做。
#
# **本入口对齐的是依赖版本，不是操作系统本身**：GitHub Actions runner 是 ubuntu-24.04，
# 本机操作系统不保证逐位一致。
#
# 冻结前仍必须跑一次**完整的 CI Epic Full**（本机 full 只等价于其中的 gate 作业，不能替代）；
# 分层判定不重新实现规则，直接调用 scripts/dev/local_layer.py（进而调用
# scripts/ci/classify_story_changes.py 的同一个 classify() 函数），因此本机结论与 CI 实际会跑
# 哪一层保证一致。

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repository_root=$(cd -- "${script_dir}/../.." && pwd)
cd "${repository_root}"

# 「工作树洁净」判定的参照基线：在做任何事之前先记一次 git 状态快照。dev-loop 下启动验证时
# 工作树本来就可能有未提交改动，这是正常状态，不是本检查要防的问题；check_git_tree_is_clean
# 事后会拿这份快照与跑完后的状态比对差异，只把**跑完后才出现**的改动判红。
initial_git_status_snapshot=$(git status --porcelain)

usage() {
  cat <<'USAGE'
用法：scripts/dev/check.sh [docs|fast|full] [选项]

选项：
  --base <ref>        分层判定的对比基线（默认 main）
  --committed-only     分层判定只看 base..HEAD 已提交差异，不含工作树未提交内容
  --print-mode         只打印分层结论（docs/fast/full），不做任何安装或检查
  --reuse-venv         复用已存在的虚拟环境，跳过默认的「每次重建」
  -h, --help           显示本帮助
USAGE
}

mode_arg=""
base_ref="main"
print_mode_only=0
committed_only=0
reuse_venv=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    docs | fast | full)
      if [[ -n "${mode_arg}" ]]; then
        printf '层级参数给了两次：先是 %s，又给了 %s。只能指定一个层级。\n' "${mode_arg}" "$1" >&2
        exit 1
      fi
      mode_arg="$1"
      shift
      ;;
    --base)
      if [[ $# -lt 2 ]]; then
        printf -- '--base 需要一个参数（对比基线），例如 --base origin/main\n' >&2
        exit 1
      fi
      base_ref="$2"
      shift 2
      ;;
    --print-mode)
      print_mode_only=1
      shift
      ;;
    --committed-only)
      committed_only=1
      shift
      ;;
    --reuse-venv)
      reuse_venv=1
      shift
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      printf '未知参数：%s\n' "$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

for required_command in git python3; do
  command -v "${required_command}" >/dev/null || {
    printf '缺少命令：%s\n' "${required_command}" >&2
    exit 1
  }
done

if [[ -z "${mode_arg}" ]]; then
  layer_args=(--base "${base_ref}")
  if [[ "${committed_only}" -eq 1 ]]; then
    layer_args+=(--committed-only)
  fi
  mode=$(python3 scripts/dev/local_layer.py "${layer_args[@]}")
  printf '本机分层判定（对比 %s，复用 classify_story_changes）：mode=%s\n' "${base_ref}" "${mode}" >&2
else
  mode="${mode_arg}"
fi

if [[ "${print_mode_only}" -eq 1 ]]; then
  printf '%s\n' "${mode}"
  exit 0
fi

# 安全解析 gate_spec.py 的 `KEY=value` 逐行输出，填进调用方传入的关联数组。
# **不用 eval**：工作流 YAML 的取值来自检出的分支内容，不受信任；`read` 只把整行
# 当纯文本赋值，永远不会把其中的内容当 shell 语法执行，天然免疫命令替换注入。
load_spec() {
  local -n out_map="$1"
  shift
  local key value
  while IFS='=' read -r key value; do
    [[ -z "${key}" ]] && continue
    # shellcheck disable=SC2034 # nameref：写 out_map 就是写调用方传入的关联数组，
    # ShellCheck 认不出 `local -n` 间接赋值，这是已知的误报模式。
    out_map["${key}"]="${value}"
  done < <("$@")
}

require_spec_key() {
  local -n map_ref="$1"
  local key="$2"
  if [[ -z "${map_ref[${key}]+set}" || -z "${map_ref[${key}]}" ]]; then
    printf 'gate_spec.py 输出里没有 %s，环境配方解析失败。\n' "${key}" >&2
    exit 1
  fi
}

# 选 Python 解释器：优先用与门禁声明版本一致的 python<major.minor>，本机没有这个版本化
# 二进制时退回裸 python3。**这一步的退回只是「尝试」，不是「承诺」**——建完虚拟环境之后
# 必须用 verify_venv_python_version 回读实际版本核对，版本不符时响亮失败，不能让脚本打印着
# 「python=3.12」却悄悄用别的版本建环境、还让 verify_repository.sh 的 `>=` 校验照样放行。
pick_python() {
  local wanted="$1"
  if command -v "python${wanted}" >/dev/null 2>&1; then
    command -v "python${wanted}"
    return 0
  fi
  command -v python3
}

verify_venv_python_version() {
  local venv_dir="$1"
  local wanted="$2"
  local actual
  actual=$("${venv_dir}/bin/python" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
  if [[ "${actual}" != "${wanted}" ]]; then
    printf '虚拟环境 %s 的解释器是 python %s，与配方声明的 %s 不符：本机大概率没有装 python%s。请安装后重试；不能用别的版本冒充，那样「与门禁一致」的说法就是假的。\n' \
      "${venv_dir}" "${actual}" "${wanted}" "${wanted}" >&2
    exit 1
  fi
  printf '虚拟环境解释器版本核对：python %s（与配方一致）\n' "${actual}" >&2
}

# 建一个只装指定 extras 的干净虚拟环境。**默认每次重建**（见文件头注释）；
# `--reuse-venv` 是显式选择的逃生口，用户自己承担「这次没有重新核验」的代价。
build_venv() {
  local venv_dir="$1"
  local python_version="$2"
  shift 2
  local install_spec=("$@")

  if [[ -d "${venv_dir}" ]]; then
    if [[ "${reuse_venv}" -eq 1 ]]; then
      printf '复用已存在的虚拟环境（--reuse-venv，未重新核验内容）：%s\n' "${venv_dir}" >&2
    else
      printf '默认重建虚拟环境（避免复用带来的假信心，--reuse-venv 可跳过）：%s\n' "${venv_dir}" >&2
      rm -rf "${venv_dir}"
    fi
  fi

  if [[ ! -d "${venv_dir}" ]]; then
    local base_python
    base_python=$(pick_python "${python_version}")
    printf '用 %s 建虚拟环境：%s\n' "${base_python}" "${venv_dir}" >&2
    if "${base_python}" -m venv "${venv_dir}" 2>/dev/null && [[ -x "${venv_dir}/bin/pip" ]]; then
      :
    elif command -v uv >/dev/null 2>&1; then
      rm -rf "${venv_dir}"
      printf '`python -m venv` 不可用或没带 pip，退回 uv venv。\n' >&2
      uv venv --python "${base_python}" "${venv_dir}" >&2
    else
      printf '无法建出可用的虚拟环境：%s -m venv 失败，且本机没有 uv 可退回。\n' "${base_python}" >&2
      exit 1
    fi
    verify_venv_python_version "${venv_dir}" "${python_version}"
  fi

  if [[ -x "${venv_dir}/bin/pip" ]]; then
    "${venv_dir}/bin/pip" install --quiet "${install_spec[@]}"
  elif command -v uv >/dev/null 2>&1; then
    uv pip install --python "${venv_dir}/bin/python" "${install_spec[@]}" >&2
  else
    printf '虚拟环境 %s 没有 pip，且本机没有 uv 可退回。\n' "${venv_dir}" >&2
    exit 1
  fi
}

# 与 gate/fast job 末尾「校验没有改写受版本控制的文件」同一条检查：本机门禁跑完不该在工作树
# 里留下未提交的改动。**与开跑前的快照比对差异，不是只跑完后判定一次**：只跑完后查一次
# `git status --porcelain` 分不清「验证过程本身改写了受版本控制的文件」（这是它真正要防的）
# 与「开跑时工作树本来就有未提交改动」（dev-loop 下的正常状态，上游真实踩过一次）。
check_git_tree_is_clean() {
  local current
  current=$(git status --porcelain)
  if [[ "${current}" == "${initial_git_status_snapshot}" ]]; then
    printf '工作树洁净：跑完后的 git 状态与开跑前完全一致，验证过程没有新增改动\n' >&2
    return 0
  fi

  local new_entries
  new_entries=$(comm -13 \
    <(printf '%s\n' "${initial_git_status_snapshot}" | sort) \
    <(printf '%s\n' "${current}" | sort))
  if [[ -z "${new_entries}" ]]; then
    printf '工作树洁净：跑完后仍处于改动状态的文件与开跑前完全相同（下列改动是你开跑前就有的，不是本次验证新增的）：\n%s\n' \
      "${current}" >&2
    return 0
  fi

  printf '本机验证过程改写了工作树（与 gate/fast job 的同名检查同一条规则）。以下文件是跑完后新增的改动——开跑前的快照里没有：\n%s\n' \
    "${new_entries}" >&2
  if [[ -n "${initial_git_status_snapshot}" ]]; then
    printf '（开跑前工作树已有以下改动，不计入上面的新增判定：\n%s\n）\n' \
      "${initial_git_status_snapshot}" >&2
  fi
  exit 1
}

run_docs() {
  scripts/ci/verify_docs.sh
}

# 在与某个 CI job 同配方的干净虚拟环境里跑仓库门禁：配方从工作流现读、venv 目录按层级分开。
run_repository_gate() {
  local job="$1"
  local workflow="$2"
  local venv_dir="$3"
  local -A spec=()
  load_spec spec python3 scripts/dev/gate_spec.py "${job}"
  for key in EXTRAS PYTHON_VERSION; do
    require_spec_key spec "${key}"
  done
  printf '%s 环境配方（现读自 %s）：extras=%s python=%s\n' \
    "${job}" "${workflow}" "${spec[EXTRAS]}" "${spec[PYTHON_VERSION]}" >&2

  mkdir -p "${repository_root}/.dev-check"
  build_venv "${venv_dir}" "${spec[PYTHON_VERSION]}" ".[${spec[EXTRAS]}]"

  # PATH 前置 venv：verify_repository.sh 里的 python3 与 shellcheck 都解析到这个干净环境。
  PATH="${venv_dir}/bin:${PATH}" scripts/ci/verify_repository.sh
  check_git_tree_is_clean
}

run_fast() {
  # Story Fast 的 fast job：无真库、无镜像。
  run_repository_gate fast .github/workflows/story.yml "${repository_root}/.dev-check/venv-fast"
}

run_full() {
  # 这里加你的真库容器配方：镜像/认证方式/库名同样由 gate_spec.py 从 ci.yml 的 gate job
  # services 现读（不要在这里另写一份）；起一次性容器（名字按 PID 生成、可用 APP_DEV_CHECK_DB_NAME
  # 覆盖，不复用、不接管既有容器）→ 等就绪 → 以 APP_ 前缀环境变量（例如 APP_DB_DSN）传给
  # verify_repository.sh → trap EXIT 清理。没有容器配方时本层 = 干净 venv 重建后跑仓库门禁。
  run_repository_gate gate .github/workflows/ci.yml "${repository_root}/.dev-check/venv-full"
}

case "${mode}" in
  docs) run_docs ;;
  fast) run_fast ;;
  full) run_full ;;
  *)
    printf '未知层级：%s（分层判定只应该产出 docs/fast/full）\n' "${mode}" >&2
    exit 1
    ;;
esac

printf '本机 %s 层验证：全部通过\n' "${mode}"

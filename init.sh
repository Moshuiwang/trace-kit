#!/usr/bin/env bash
# trace-kit init.sh：把 template/ 提升到仓库根目录，删除套件自身文件。
#
#   gh repo create <新仓> --public --template Moshuiwang/trace-kit --clone && cd <新仓> && ./init.sh
#
# 只在「从 trace-kit 模板新建的仓库」根目录运行一次；脚本不提交——运行完成后由你执行 git add -A 并提交（末尾会打印步骤）。
# 出处：套件安装两步由产品负责人 2026-09-02 指定（Trace #1 合同 §1）。
set -euo pipefail

main() {
  local root kit_version
  root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
  cd "${root}"
  if [[ ! -d template ]]; then
    printf '找不到 template/：本脚本只在从 trace-kit 模板新建的仓库根目录运行一次。\n' >&2
    exit 1
  fi
  if ! git rev-parse --show-toplevel >/dev/null 2>&1 || [[ "$(git rev-parse --show-toplevel)" != "${root}" ]]; then
    printf '当前目录不是 git 仓库根目录。\n' >&2
    exit 1
  fi
  if [[ -n "$(git status --porcelain)" ]]; then
    printf '工作树不洁净：先提交或清理再运行，init 之后才能一眼看出它改了什么。\n' >&2
    exit 1
  fi
  kit_version=$(sed -nE 's/^## \[([0-9]+\.[0-9]+\.[0-9]+)\].*/\1/p' CHANGELOG.md | head -1)
  printf 'trace-kit %s：提升 template/ 到仓库根目录\n' "${kit_version:-未知版本}"

  # 套件自身的文件：新项目不需要，先删再复制，避免同名目录叠合。
  rm -rf plugin examples METHOD.md CHANGELOG.md README.md docs .claude-plugin scripts/kit \
    .github/workflows/kit-selfcheck.yml
  rmdir scripts .github/workflows .github 2>/dev/null || true

  # 含点文件一起复制（.github / .gitignore / .dockerignore）。
  cp -a template/. .
  rm -rf template

  printf '完成。下一步：\n'
  printf '  1. git add -A && git commit -m "chore: 从 trace-kit %s 初始化"\n' "${kit_version:-}"
  printf '  2. 按 README.md「怎么用」清单替换项目名（app）与产品文档\n'
  printf '  3. claude plugin marketplace add Moshuiwang/trace-kit && claude plugin install trace-kit@trace-kit\n'
  # 最后一步删除自己：函数体已整体解析，删除不影响本次执行。
  rm -f -- "${root}/init.sh"
}

main "$@"

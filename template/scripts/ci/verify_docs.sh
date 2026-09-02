#!/usr/bin/env bash
# 不安装依赖、不启动数据库或 Docker 的文档门禁。
# 出处：lingxi https://github.com/Moshuiwang/lingxi/pull/12（2026-07-25 CI 基线）；验证：298 个 PR。
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repository_root=$(cd -- "${script_dir}/../.." && pwd)
cd "${repository_root}"

python3 scripts/ci/check_markdown_links.py
python3 scripts/ci/check_acceptance_matrix.py
# 验收矩阵单行体量棘轮：已超 800B 的 V-* 断言行只许缩不许涨，未超的不得新超；
# 总量触发线只提示不卡红。
python3 scripts/ci/check_matrix_row_size_ratchet.py
# 归属核对也接进纯文档路径：登记表里半数以上条目指向 docs/ 下的 .md，纯文档 PR 是它们
# 唯一可能被改动的入口——只接进 verify_repository.sh 等于给这些登记留了一条从不核对的路径
# （上游三路独立复查实测坐实：往技术设计追加一条未登记的归属，纯文档门禁曾照样 EXIT=0）。
python3 scripts/ci/check_contract_attribution.py
# 开工必读集体量预算：必读文档合计字节数设硬上限，超限即红——防膨胀的结构性门禁。
python3 scripts/ci/check_docs_size_budget.py

whitespace_files=$(git grep -Il -E '[[:blank:]]+$' -- . ':!.tmp/**' || true)
if [[ -n "${whitespace_files}" ]]; then
  printf '以下正式文件包含行尾空白：\n%s\n' "${whitespace_files}" >&2
  exit 1
fi

echo '文档门禁：全部通过'

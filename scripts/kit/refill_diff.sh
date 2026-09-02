#!/usr/bin/env bash
# 自回灌（自验证①）：template 与 lingxi 对应文件逐对 diff，lingxi 侧的差异行按 G3 关键词分类，
# 未命中关键词的行列出供人工复核（结论写进 Trace 的验收.md）。只读 lingxi。
#
#   scripts/kit/refill_diff.sh <lingxi 仓库路径> [lingxi 提交=caa845d] > 报告.md
#
# 出处：Trace #1 合同 §4「自回灌」；分级清单「自验证口径」。
set -euo pipefail
lingxi=${1:?用法：refill_diff.sh <lingxi 仓库路径> [提交]}
ref=${2:-caa845d}
kit=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
cd "${kit}"

# template 路径 : lingxi 路径
pairs=(
  "template/AGENTS.md:AGENTS.md"
  "template/CLAUDE.md:CLAUDE.md"
  "template/CHANGELOG.md:CHANGELOG.md"
  "template/.gitignore:.gitignore"
  "template/.dockerignore:.dockerignore"
  "template/Dockerfile:Dockerfile"
  "template/pyproject.toml:pyproject.toml"
  "template/.github/copilot-instructions.md:.github/copilot-instructions.md"
  "template/.github/PULL_REQUEST_TEMPLATE.md:.github/PULL_REQUEST_TEMPLATE.md"
  "template/.github/ISSUE_TEMPLATE/change.yml:.github/ISSUE_TEMPLATE/change.yml"
  "template/.github/ISSUE_TEMPLATE/decision.yml:.github/ISSUE_TEMPLATE/decision.yml"
  "template/.github/ISSUE_TEMPLATE/research.yml:.github/ISSUE_TEMPLATE/research.yml"
  "template/.github/ISSUE_TEMPLATE/bug.yml:.github/ISSUE_TEMPLATE/bug.yml"
  "template/.github/workflows/story.yml:.github/workflows/story.yml"
  "template/.github/workflows/ci.yml:.github/workflows/ci.yml"
  "template/.github/workflows/publish.yml:.github/workflows/publish.yml"
  "template/.github/workflows/docs.yml:.github/workflows/docs.yml"
  "template/docs/README.md:docs/README.md"
  "template/docs/产品合同.md:docs/产品合同与外部边界.md"
  "template/docs/当前能力.md:docs/当前能力.md"
  "template/docs/协作约定.md:docs/协作约定.md"
  "template/docs/协作/执行方法.md:docs/协作/开工计划模板.md"
  "template/docs/决策记录/README.md:docs/决策记录/README.md"
  "template/docs/参考证据/README.md:docs/参考证据/README.md"
  "template/docs/技术设计/README.md:docs/技术设计/README.md"
  "template/docs/技术设计/验证与门禁.md:docs/技术设计/验证与门禁.md"
  "template/docs/技术设计/验收矩阵.md:docs/技术设计/验收矩阵.md"
  "template/docs/traces/README.md:docs/traces/README.md"
  "template/scripts/ci/classify_story_changes.py:scripts/ci/classify_story_changes.py"
  "template/scripts/ci/check_markdown_links.py:scripts/ci/check_markdown_links.py"
  "template/scripts/ci/check_acceptance_matrix.py:scripts/ci/check_acceptance_matrix.py"
  "template/scripts/ci/check_matrix_row_size_ratchet.py:scripts/ci/check_matrix_row_size_ratchet.py"
  "template/scripts/ci/check_docs_size_budget.py:scripts/ci/check_docs_size_budget.py"
  "template/scripts/ci/check_contract_attribution.py:scripts/ci/check_contract_attribution.py"
  "template/scripts/ci/check_size_ratchet.py:scripts/ci/check_size_ratchet.py"
  "template/scripts/ci/write_epic_candidate.py:scripts/ci/write_epic_candidate.py"
  "template/scripts/ci/verify_epic_candidate.py:scripts/ci/verify_epic_candidate.py"
  "template/scripts/ci/verify_docs.sh:scripts/ci/verify_docs.sh"
  "template/scripts/ci/verify_repository.sh:scripts/ci/verify_repository.sh"
  "template/scripts/ci/check_deploy_contract.py:scripts/ci/check_deploy_contract.py"
  "template/scripts/ci/verify_compose_structure.sh:scripts/ci/verify_compose_structure.sh"
  "template/scripts/dev/check.sh:scripts/dev/check.sh"
  "template/scripts/dev/gate_spec.py:scripts/dev/gate_spec.py"
  "template/scripts/dev/local_layer.py:scripts/dev/local_layer.py"
  "template/scripts/dev/README.md:scripts/dev/README.md"
  "template/scripts/ops/host_health_alert.py:scripts/ops/host_health_alert.py"
  "template/deploy/compose.yaml:deploy/compose.yaml"
  "template/deploy/compose.stage.yaml:deploy/compose.stage.yaml"
  "template/deploy/compose.prod.yaml:deploy/compose.prod.yaml"
  "template/deploy/.env.example:deploy/.env.example"
  "template/deploy/README.md:deploy/README.md"
  "template/deploy/生产部署runbook.md:deploy/生产部署runbook.md"
  "template/deploy/验收前部署配置清单.md:deploy/验收前部署配置清单.md"
  "template/deploy/监控告警.md:deploy/监控告警.md"
)

# lingxi 侧差异行命中其一即视为 G3（产品名词 / lingxi 内部标识 / 被裁掉的 lingxi 专属机制）。
g3='lingxi|Lingxi|LINGXI|代码框架|Codex|codex|灵犀|飞书|Bot-|百炼|MCP|Agent SDK|Claude Code \+|银河|花名册|JumpServer|Supabase|biai|biplus|权限|开通|问数|管理员|交付|投递|卡片|会话|scheduler|gateway|worker|reauthorize|oauth|OAuth|alembic|migration|content\.toml|翻译|令牌|凭据|extras|npm|node|Node|四镜像|四个镜像|双构建|Issue #|#[0-9]{2,3}|PR #|V-[^示]|src/lingxi|tests/test_|通报|采集|审计|内测|Epic [A-Z]|S-[A-Z]|Trace #|2026-0[789]-[0-9]{2}|L1 |L3 |permission|galaxy|feishu|docx|tmpfs|LINGXI_|lingxi-|admin|Admin|/admin|记忆|表格|文档交付|高级工作台|旧系统|存量|职位|公司|指标|Story Fast|Epic Full|Main Publish|lark|CardKit|Bridge|百炼|受控|真库|PostgreSQL|postgres|Supabase|shellcheck|Python|python'

printf '# 自回灌 diff 报告（template ⟷ lingxi %s）\n\n' "${ref}"
printf '| template 文件 | lingxi 对应 | lingxi 行数 | template 行数 | lingxi 侧差异行 | 命中 G3 | 未命中（人工复核） |\n'
printf '| --- | --- | ---: | ---: | ---: | ---: | ---: |\n'
tmpdir=$(mktemp -d -t refill-XXXXXX)
trap 'rm -rf "${tmpdir}"' EXIT
appendix="${tmpdir}/appendix.md"
: > "${appendix}"
for pair in "${pairs[@]}"; do
  t=${pair%%:*}
  l=${pair#*:}
  if ! git -C "${lingxi}" cat-file -e "${ref}:${l}" 2>/dev/null; then
    printf '| `%s` | `%s` | — | — | lingxi 无此文件 | — | — |\n' "${t}" "${l}"
    continue
  fi
  git -C "${lingxi}" show "${ref}:${l}" > "${tmpdir}/lingxi.txt"
  if [[ ! -f "${t}" ]]; then
    printf '| `%s` | `%s` | %s | — | **template 缺文件** | — | — |\n' "${t}" "${l}" "$(wc -l < "${tmpdir}/lingxi.txt")"
    continue
  fi
  diff -u "${tmpdir}/lingxi.txt" "${t}" > "${tmpdir}/d.txt" || true
  grep -E '^-' "${tmpdir}/d.txt" | grep -vE '^---' | sed 's/^-//' > "${tmpdir}/removed.txt" || true
  removed=$(wc -l < "${tmpdir}/removed.txt")
  hit=$(grep -cE "${g3}" "${tmpdir}/removed.txt" || true)
  grep -vE "${g3}" "${tmpdir}/removed.txt" | grep -vE '^\s*$' | grep -vE '^\s*[-|#>*]?\s*$' > "${tmpdir}/miss.txt" || true
  miss=$(wc -l < "${tmpdir}/miss.txt")
  printf '| `%s` | `%s` | %s | %s | %s | %s | %s |\n' "${t}" "${l}" "$(wc -l < "${tmpdir}/lingxi.txt")" "$(wc -l < "${t}")" "${removed}" "${hit}" "${miss}"
  if [[ "${miss}" -gt 0 ]]; then
    {
      printf '\n### `%s` ⟵ `%s`：未命中 G3 关键词的 lingxi 侧行（%s 行，最多列 40）\n\n' "${t}" "${l}" "${miss}"
      head -40 "${tmpdir}/miss.txt" | sed 's/^/    /'
    } >> "${appendix}"
  fi
done
printf '\n## 附录：待人工复核的行\n'
cat "${appendix}"

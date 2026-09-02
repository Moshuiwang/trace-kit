#!/usr/bin/env bash
# 无网络、无业务系统副作用的仓库基础质量门禁。
# 出处：lingxi https://github.com/Moshuiwang/lingxi/pull/12（2026-07-25 CI 基线；PR #48 半开守卫）；验证：298 个 PR。
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repository_root=$(cd -- "${script_dir}/../.." && pwd)
cd "${repository_root}"

for required_command in git python3 shellcheck; do
  command -v "${required_command}" >/dev/null || {
    printf '缺少 CI 命令：%s\n' "${required_command}" >&2
    exit 1
  }
done

# 门禁必须跑在项目声明支持的解释器上。裸 python3 在 CI 上恰好是 3.12 所以不会暴露，
# 但本地 python3 可能是 3.9——那样门禁会在一个项目不支持的解释器上给出绿灯，
# 属于假信心，比没有门禁更危险。
declared_python=$(sed -nE -e 's/^requires-python = ">=([0-9]+\.[0-9]+)"$/\1/p' pyproject.toml)
if [[ -z "${declared_python}" ]]; then
  printf 'pyproject.toml 里读不到 requires-python，无法校验解释器版本。\n' >&2
  exit 1
fi
actual_python=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
if ! python3 -c 'import sys; d=sys.argv[1].split("."); sys.exit(0 if sys.version_info[:2] >= (int(d[0]), int(d[1])) else 1)' "${declared_python}"; then
  printf 'python3 是 %s，低于 pyproject.toml 声明的 %s。请用 python%s 运行本门禁。\n' \
    "${actual_python}" "${declared_python}" "${declared_python}" >&2
  exit 1
fi
printf '解释器版本：python3 = %s，满足声明的 >=%s\n' "${actual_python}" "${declared_python}"

tracked_scripts=()
while IFS= read -r script_path; do
  tracked_scripts+=("${script_path}")
done < <(git ls-files 'scripts/*.sh' 'tests/*.sh' 'deploy/*.sh')

if ((${#tracked_scripts[@]} == 0)); then
  printf '没有找到受版本控制的 Bash 脚本。\n' >&2
  exit 1
fi

bash -n "${tracked_scripts[@]}"
printf 'Bash 语法：通过\n'

shellcheck --severity=warning "${tracked_scripts[@]}"
# 打印版本：本机与 CI 装了不同版本的 linter，是一种不会报错的分歧。
# 版本只在 pyproject.toml 的 dev 组锁一次，CI 与本机都用 `pip install '.[dev]'` 取得同一个。
printf 'ShellCheck：通过（%s）\n' "$(shellcheck --version | sed -n 's/^version: //p')"

python3 scripts/ci/check_markdown_links.py
# 验收矩阵的三态状态列与合同章节覆盖清单。这两样只作散文约定时：
# 断言可以没人认领、合同可以新增一节而没有任何断言，门禁照样全绿。
python3 scripts/ci/check_acceptance_matrix.py
# 文件体量棘轮：已超过阈值（1500 行）的文件登记在 scripts/ci/size_ratchet_baseline.txt 里，
# 只许变小、不许变大；未超阈值的文件不得新超过阈值。基线由 --refresh 生成，拒绝被手工调大。
python3 scripts/ci/check_size_ratchet.py
python3 scripts/ci/check_matrix_row_size_ratchet.py
# 归属核对：把某句规则的权威记成产品合同本身的断言，必须能在 docs/产品合同.md 正文里找到
# 对应登记，找不到就红。核对的是「归属已登记、登记与源句均未过期」，
# 不是判定这句话在语义上是否真的成立（见 check_contract_attribution.py 头注释）。
python3 scripts/ci/check_contract_attribution.py
# 开工必读集体量预算：必读文档合计字节数设硬上限，超限即红。
python3 scripts/ci/check_docs_size_budget.py
# 部署编排的静态契约（deploy/ 由部署骨架提供）：job 无 restart、镜像 tag 不可变、
# 凭据不入库、生产零构建、非 root。刻意不依赖 docker 与 YAML 库，
# 这样一台没装 docker 的开发机也能跑出与 CI 相同的结论。
python3 scripts/ci/check_deploy_contract.py

# 这里加你的真库半开守卫：设置了容器却没给 DSN 时，真库断言会被静默跳过、门禁却照样绿，
# 这种「看起来跑了真库」的假信心必须直接失败（环境变量一律 APP_ 前缀，例如
# APP_DB_CONTAINER / APP_DB_DSN）。

if [[ -d tests ]]; then
  PYTHONPATH=src python3 -m unittest discover -s tests -v
  printf 'Python 自动测试：通过\n'
fi

whitespace_files=$(git grep -Il -E '[[:blank:]]+$' -- . ':!.tmp/**' || true)
if [[ -n "${whitespace_files}" ]]; then
  printf '以下正式文件包含行尾空白：\n%s\n' "${whitespace_files}" >&2
  exit 1
fi
printf '行尾空白：通过\n'

sensitive_config_files=$(
  git ls-files |
    awk -F/ '
      $NF == ".env" { print; next }
      $NF ~ /^\.env\./ && $NF != ".env.example" { print }
    '
)
if [[ -n "${sensitive_config_files}" ]]; then
  printf '以下敏感配置文件不应进入版本控制：\n%s\n' "${sensitive_config_files}" >&2
  exit 1
fi

private_key_files=$(
  git grep -Il -E -- '-----BEGIN ([A-Z0-9]+ )?PRIVATE KEY-----' -- . || true
)
if [[ -n "${private_key_files}" ]]; then
  printf '以下文件疑似包含私钥：\n%s\n' "${private_key_files}" >&2
  exit 1
fi
printf '敏感配置文件：通过\n'

printf 'CI 基础质量门禁：全部通过\n'

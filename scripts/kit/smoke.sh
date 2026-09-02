#!/usr/bin/env bash
# 空项目冒烟（自验证②的机械部分）：把套件当作模板起一个空项目（临时目录，不建远端仓），
# 跑 init.sh，然后在新项目里跑全部本机门禁。用法：
#
#   scripts/kit/smoke.sh [--strict] [目标目录]
#
# --strict：任何「未执行项」（本机缺 docker compose / PyYAML）都判红，CI 用。
# 成功后保留目标目录供人工检查（默认 mktemp），由调用者清理。
# 出处：Trace #1 合同 §4「空项目冒烟」；lingxi #236 本机=CI 同构纪律。
set -euo pipefail

strict=0
work=""
for arg in "$@"; do
  case "${arg}" in
    --strict) strict=1 ;;
    *) work="${arg}" ;;
  esac
done
kit=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work=${work:-$(mktemp -d -t trace-kit-smoke-XXXXXX)}
mkdir -p "${work}"
if [[ -n "$(ls -A "${work}")" ]]; then
  printf '目标目录非空：%s\n' "${work}" >&2
  exit 1
fi

git_smoke() { git -c user.name=smoke -c user.email=smoke@example.invalid "$@"; }

printf '== 0/6 模拟 gh repo create --template：拷贝受版本控制的套件文件到 %s\n' "${work}"
(cd "${kit}" && git ls-files -z | tar --null -T - -cf -) | (cd "${work}" && tar -xf -)
cd "${work}"
git init -q -b main
git_smoke add -A
git_smoke commit -qm "从 trace-kit 模板新建"
./init.sh
git_smoke add -A
git_smoke commit -qm "chore: 从 trace-kit 初始化"

unverified=()
printf '== 1/6 文档门禁（verify_docs.sh）\n'
scripts/ci/verify_docs.sh
printf '== 2/6 本机三层（check.sh docs / fast / full）\n'
scripts/dev/check.sh docs
scripts/dev/check.sh fast
scripts/dev/check.sh full
printf '== 3/6 部署契约（文本级）\n'
python3 -B scripts/ci/check_deploy_contract.py
printf '== 4/6 compose 结构对照（需要 docker compose）\n'
if docker compose version >/dev/null 2>&1; then
  scripts/ci/verify_compose_structure.sh
else
  unverified+=("scripts/ci/verify_compose_structure.sh（本机无 docker compose）")
fi
printf '== 5/6 工作流 YAML 可解析\n'
if python3 -c 'import yaml' >/dev/null 2>&1; then
  python3 - <<'PY'
import pathlib, sys, yaml
bad = 0
for path in sorted(pathlib.Path(".github/workflows").glob("*.yml")):
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(doc, dict) and "jobs" in doc, "缺 jobs"
        print(f"  {path}: {len(doc['jobs'])} jobs")
    except Exception as exc:  # noqa: BLE001
        bad += 1
        print(f"  {path}: 解析失败：{exc}", file=sys.stderr)
sys.exit(1 if bad else 0)
PY
else
  unverified+=("工作流 YAML 解析（本机无 PyYAML）")
fi
printf '== 6/6 门禁没有改写工作树\n'
if [[ -n "$(git status --porcelain)" ]]; then
  printf '门禁改写了工作树：\n' >&2
  git status --porcelain >&2
  exit 1
fi

printf '冒烟完成：%s\n' "${work}"
if ((${#unverified[@]})); then
  printf '未执行项（如实列出）：\n' >&2
  printf '  - %s\n' "${unverified[@]}" >&2
  if [[ "${strict}" -eq 1 ]]; then
    printf -- '--strict：未执行项判红\n' >&2
    exit 1
  fi
fi

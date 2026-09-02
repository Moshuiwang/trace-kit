#!/usr/bin/env bash
# 套件禁词扫描：template/ 与 plugin/ 不得含 lingxi 产品名词、主机名、本机路径、凭据形态；
# 只允许出现在「出处」行里的 lingxi 链接。examples/ 不在扫描范围（G3 档本就是 lingxi 特有）。
# 出处：Trace #1 合同 §2「显式除外」与分级清单 E 节（铁律 1 / 2）。
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."

pattern='lingxi|LINGXI|灵犀|飞书|Bot-Test|Bot-Prod|百炼|MCP|Agent SDK|银河|花名册|JumpServer|Supabase|biai|biplus|/home/[^/ ]+/|E-021|oc_[a-z0-9]{6}|cli_[a-z0-9]{6}|ou_[a-z0-9]{6}|ghs_[A-Za-z0-9]|ghp_[A-Za-z0-9]|gho_[A-Za-z0-9]'
# 全仓（含 docs/traces、examples）都不得出现本机 / 主机 / 凭据形态；本文件与 refill_diff.sh 的关键词表除外。
machine_pattern='/home/[^/ ]+/|TZ-server|biai-|biplus|oc_[a-z0-9]{6}|cli_[a-z0-9]{6}|ou_[a-z0-9]{6}|ghs_[A-Za-z0-9]|ghp_[A-Za-z0-9]|gho_[A-Za-z0-9]'
targets=(template plugin .claude-plugin)
hits=$(grep -rnIE "${pattern}" "${targets[@]}" 2>/dev/null | grep -vE 'github\.com/Moshuiwang/lingxi|examples/lingxi/' || true)
if [[ -n "${hits}" ]]; then
  printf '禁词命中（template / plugin 只允许在「出处」行引用 lingxi 链接）：\n%s\n' "${hits}" >&2
  exit 1
fi
machine_hits=$(git grep -nIE "${machine_pattern}" -- . ':!scripts/kit/check_no_lingxi.sh' ':!scripts/kit/refill_diff.sh' || true)
if [[ -n "${machine_hits}" ]]; then
  printf '全仓不得出现本机路径 / 主机名 / 凭据形态：\n%s\n' "${machine_hits}" >&2
  exit 1
fi
printf '禁词扫描：通过（%s；全仓机器事实零命中）\n' "${targets[*]}"

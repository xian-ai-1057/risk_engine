#!/usr/bin/env bash
# risk_analysis.exe smoke test (POSIX/Bash).
#
# 用途：在打包出 exe 後驗證合約欄位與併發行為。
#
# 用法:
#   bash scripts/smoke_test.sh <path-to-exe> <path-to-sample-dir>
#
# sample-dir 必須包含：
#   indicators_config.json
#   risk_user_prompt.txt
#   narrative_user_prompt.txt
#   f1.html f2.html f3.html f4.html  ← 4 個 HTML 財報
#   (選用) tag_table.csv
#
# 需求：jq

set -euo pipefail

EXE="${1:?usage: smoke_test.sh <exe> <sample-dir>}"
SAMPLE="${2:?usage: smoke_test.sh <exe> <sample-dir>}"
INDUSTRY="${INDUSTRY:-7大指標}"

if ! command -v jq >/dev/null 2>&1; then
    echo "[FAIL] 需要安裝 jq" >&2
    exit 1
fi

if [[ ! -x "$EXE" ]]; then
    echo "[FAIL] exe 不存在或不可執行: $EXE" >&2
    exit 1
fi

# 把 sample 同層資源複製到 exe 同層
EXE_DIR="$(cd "$(dirname "$EXE")" && pwd)"
for f in indicators_config.json risk_user_prompt.txt \
         narrative_user_prompt.txt tag_table.csv; do
    if [[ -f "$SAMPLE/$f" ]]; then
        cp "$SAMPLE/$f" "$EXE_DIR/"
    fi
done

# 4 個 HTML
HTML_FILES=()
for n in f1 f2 f3 f4; do
    p="$SAMPLE/${n}.html"
    if [[ ! -f "$p" ]]; then
        echo "[FAIL] 找不到 $p" >&2
        exit 1
    fi
    HTML_FILES+=("$p")
done

# ── 1. 單次呼叫：合約欄位 ──────────────────────
echo "== 測試 1: 單次呼叫契約 =="
out="$("$EXE" "${HTML_FILES[@]}" \
    --industry "$INDUSTRY" \
    --request-id "smoke-1" --stdout)"

echo "$out" | jq -e '
    .schema_version == "1.0"
    and (.request_id == "smoke-1")
    and (.risk_prompt | type == "string" and length > 0)
    and (.narrative_prompt | type == "string" and length > 0)
    and (.risk_report | type == "object")
    and (.grouped_report | type == "object")
' >/dev/null || { echo "[FAIL] 合約欄位不齊"; echo "$out" | head; exit 1; }

# 檢查 risk_prompt 中 placeholder 已替換
echo "$out" | jq -r '.risk_prompt' \
    | grep -qE '\{\{risk_results_[0-9]\}\}' \
    && { echo "[FAIL] risk_prompt 殘留未替換的 {{risk_results_N}}"; exit 1; } \
    || true

echo "[OK] 契約欄位齊備"

# ── 2. 錯誤路徑：缺 industry → INVALID_ARGS ──────
echo "== 測試 2: INVALID_ARGS =="
err="$("$EXE" "${HTML_FILES[@]}" \
    --request-id "smoke-2" --stdout 2>/dev/null \
    || true)"
ec="$(echo "$err" | jq -r '.error_code' 2>/dev/null || echo "")"
[[ "$ec" == "INVALID_ARGS" ]] \
    || { echo "[FAIL] 期待 INVALID_ARGS 實際 $ec"; exit 1; }
echo "[OK] error_code=INVALID_ARGS"

# ── 3. 併發 5 次：request_id 不互相覆蓋 ──────────
echo "== 測試 3: 併發 5 次 =="
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
pids=()
for i in 1 2 3 4 5; do
    (
        "$EXE" "${HTML_FILES[@]}" \
            --industry "$INDUSTRY" \
            --request-id "smoke-c$i" --stdout \
            > "$TMP/out_$i.json"
    ) &
    pids+=("$!")
done
for p in "${pids[@]}"; do wait "$p"; done

for i in 1 2 3 4 5; do
    rid="$(jq -r '.request_id' < "$TMP/out_$i.json")"
    [[ "$rid" == "smoke-c$i" ]] \
        || { echo "[FAIL] 第 $i 份 request_id 錯誤: $rid"; exit 1; }
done
echo "[OK] 5 份併發各自獨立"

echo "OK"

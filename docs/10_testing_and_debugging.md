# 10 測試與除錯

本檔是新人除錯時的速查；測試組成的權威說明見 [tests/README.md](../tests/README.md)，環境變數與 logging 完整規格見專案根 [README.md](../README.md)。

## 1 pytest 速查

```bash
pytest                                              # 全部 92 個測試
pytest tests/test_formula.py                        # 單檔
pytest tests/test_checker.py::TestCheckCompound     # 單類別
pytest tests/test_formula.py::TestSafeEval::test_division_by_zero  # 單測試
pytest --cov=risk_engine --cov=utils                # 覆蓋率
pytest --cov=risk_engine --cov=utils --cov-report=html  # HTML 覆蓋率
```

各測試檔涵蓋的模組與測試類別組成見 [tests/README.md](../tests/README.md)（為權威來源）。

---

## 2 Log 解讀

### 2.1 Log 檔位置

未指定 `--log` 時：

```
<base_dir>/outputs/log/<YYYYMMDD_HHMMSS>[_<request_id>].log
```

| 環境 | base_dir |
|------|----------|
| 非 EXE（開發） | `src/` 上層（即專案根） |
| EXE（PyInstaller 打包） | 執行檔目錄 |

由 [`paths.get_base_dir`](../src/risk_engine/paths.py) 決定。

### 2.2 Log 級別

- 預設 `INFO`。
- CLI `--debug` 切 `DEBUG`，會看到完整公式求值過程、規則分派過程、placeholder 替換過程。

### 2.3 Log 格式

```
%(asctime)s [%(levelname)s] %(name)s - %(message)s
```

`%(name)s` 是模組名（如 `risk_engine.report`），方便 grep。

### 2.4 常用 grep

```bash
# 看哪些 placeholder 被配對
grep "已配對\|未配對" log/*.log

# 看公式求值的失敗
grep "公式求值\|formula" log/*.log | grep -i "error\|warn\|missing"

# 看 Pipeline 各步驟耗時
grep "Pipeline\|filter_and_group\|build_narrative\|build_risk" log/*.log
```

---

## 3 常見錯誤對應

### 3.1 載入錯誤

| 錯誤 | 原因 | 修復 |
|------|------|------|
| `ConfigError: 產業 'xxx' 不存在` | xlsx「產業別」欄與 `--industry` 旗標不符 | 檢查兩邊的字串是否完全相同（含空白）。 |
| `ConfigError: 設定檔不存在: ...` | xlsx 路徑錯 / EXE 同層沒有 xlsx | `--xlsx` 指定路徑，或把 xlsx 放到 EXE 同層並用預設檔名（`指標.xlsx` / `indicator.xlsx` / `indicators.xlsx`）。 |
| `ReportLoadError: CSV 缺少欄位 'FA_RFNBR'` | CSV 不是 risk_engine 預期的格式 | 用 [`utils/csv_to_report_json.py`](../src/utils/csv_to_report_json.py) 轉換，或檢查 CSV header。 |
| `ReportLoadError: 無效的 JSON` | 財報 JSON 結構壞掉 | `python -m json.tool report.json` 驗證。 |
| `UnicodeDecodeError`（讀 HTML 時） | HTML 不是 Big5 編碼 | 確認上游系統輸出的 HTML 編碼。 |

### 3.2 規則判定異常

| 症狀 | 可能原因 |
|------|---------|
| 規則 `status=missing`，但代碼明明在財報裡 | 公式裡含非法字元（`%` 不是運算子）；代碼後綴錯（`_PRE` 而非 `_PRV`）；對應期別為 `null`。 |
| 規則 `status=missing`，門檻是 compound | 條件樹中至少一個葉節點缺值，而且沒有短路（AND 沒 false / OR 沒 true）。 |
| AND/OR 解析跟想像不同 | OR 優先解析。請用括號明確化（見 [08_config_authoring.md#or-優先解析陷阱](08_config_authoring.md#or-優先解析陷阱)）。 |

### 3.3 EXE 退出碼

| exit code | `error_code` | 觸發時機 |
|-----------|--------------|---------|
| 1 | `INVALID_ARGS` | 參數驗證失敗 / stdin JSON 解析失敗 |
| 2 | `MISSING_FILE` | 必要檔案不存在（xlsx / prompt 模板 / HTML） |
| 2 | `CONFIG_ERROR` | xlsx 解析失敗 / 報表載入失敗 / 產業不存在 |
| 3 | `PROCESSING_ERROR` | 其他未預期例外 |

`--stdout` 模式下會印出 `ExeError` JSON：

```json
{
  "error": "...",
  "error_code": "CONFIG_ERROR",
  "request_id": "ab12cd34"
}
```

對應實作：[`scripts/main.py::_exit_error`](../scripts/main.py)。

---

## 4 建議的 debug 流程

當你的規則判定不如預期時，照下面順序逼近：

### Step 1：先跑 pytest

```bash
pytest -v
```

如果原本通過的測試壞了，先恢復。

### Step 2：用 legacy CLI 加 `--debug`

Legacy CLI 比 EXE 快很多（不必解析 HTML），DEBUG log 看得到求值細節。

```bash
python scripts/risk_checker.py \
    --report inputs/json_sample/sample_report.json \
    --config /tmp/indicator.json \
    --industry 7大指標 \
    -o /tmp/result.json \
    --debug 2>&1 | tee /tmp/debug.log
```

打開 `/tmp/debug.log`，搜：

- 你關心的 `tag_id` → 看判定過程
- 你關心的 formula → 看代碼替換 + 求值結果

### Step 3：對照範例 JSON

| 範例 | 用途 |
|------|------|
| [inputs/json_sample/risk_sample.json](../inputs/json_sample/risk_sample.json) | 完整 `FullReport`，看每個欄位該長什麼樣 |
| [inputs/json_sample/risk_prompt_input_sample.json](../inputs/json_sample/risk_prompt_input_sample.json) | `to_prompt_view` 投影後，送進 LLM 的版本 |
| [inputs/json_sample/group_sample.json](../inputs/json_sample/group_sample.json) | `GroupedReport` 範例 |

### Step 4：寫一個 mini 測試

把 bug 的最小重現寫成 pytest 測試，加進 [`tests/`](../tests/) 對應檔。修完之後這條測試會永久守住這個 bug。

範例（取自 `test_checker.py`）：

```python
def test_compound_or_priority(self):
    """A AND B OR C 應解析為 or(and(A,B), C)。"""
    result = parse_threshold("A AND B OR C")
    tree = result["condition_tree"]
    assert tree["node_type"] == "or"
    assert tree["children"][0]["node_type"] == "and"
```

### Step 5：跑 EXE 流程做完整驗證

最後再跑一次 `scripts/main.py`，確認 ExeOutput 的對外契約沒壞。

---

## 5 Tip：可重現的測試環境

[`tests/`](../tests/) 大量使用 pytest 的 `tmp_path` fixture 建臨時檔案，避免污染專案目錄。新增測試時請延續這個慣例。

```python
def test_load_csv_missing_key(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("name,value\nfoo,1\n", encoding="utf-8")
    with pytest.raises(ReportLoadError, match="FA_RFNBR"):
        load_report(str(p))
```

詳細慣例見 [tests/README.md#fixture-使用](../tests/README.md#fixture-使用)。

---

## 6 不確定改哪裡？

回 [07_module_reference.md](07_module_reference.md) 看「分類速查」表，先確認你要改的檔案屬於 EXE 路徑、Legacy、還是 One-off 工具。改 EXE 路徑要更謹慎；One-off 工具相對自由。

如果還是不確定，寫一個失敗中的 pytest 測試，再去問 git 紀錄誰最後動過該檔案：

```bash
git log -p --follow src/risk_engine/<檔名>.py
```

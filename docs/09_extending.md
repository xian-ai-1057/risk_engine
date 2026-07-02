# 09 擴展指南

四種擴展類型，按改動範圍由小到大排序。

## 1 新增中文門檻格式

**只動 [`threshold.py`](../src/risk_engine/threshold.py) + 測試**。

例：要支援「持平於前期 ±5%」這種寫法。

### 步驟

1. 在 [`threshold.parse_threshold`](../src/risk_engine/threshold.py) 增加 `re.match` 分支，回傳含 `compare_type` 的 dict。
2. 如果是新的 `compare_type`，要連帶在 `checker.py` 補對應 handler（見 §2）。如果只是新格式 → 沿用既有 `compare_type` 就只要動 threshold。
3. 在 [`tests/test_threshold.py`](../tests/test_threshold.py) 新增測試類別（照抄既有的 `TestAbsoluteThreshold` 結構）。

### 模板

```python
# threshold.py，加在 parse_threshold 內既有分支之間
m = re.match(r"持平於前期±(\d+(?:\.\d+)?)%", first_line)
if m:
    return {
        "compare_type": "period_change_pct",
        "direction": "stable",
        "operator": "<=",
        "threshold": float(m.group(1)),
    }
```

```python
# tests/test_threshold.py
class TestStableThreshold:
    def test_stable_within_5pct(self):
        result = parse_threshold("持平於前期±5%")
        assert result["compare_type"] == "period_change_pct"
        assert result["direction"] == "stable"
        assert result["threshold"] == 5.0
```

### 驗證

```bash
pytest tests/test_threshold.py -v
```

---

## 2 新增比較類型（`compare_type`）

**動 [`checker.py`](../src/risk_engine/checker.py) + [`threshold.py`](../src/risk_engine/threshold.py) + 測試**。

例：要支援「跨期變動率（前期 → 前前期）」這種比較類型。

### 步驟

1. 在 [`checker.py`](../src/risk_engine/checker.py) 撰寫 `_check_<name>(current_val, prev_val, rule, report=None)` 函式，回傳 `TagResult`。
2. 在 `_HANDLERS`（檔案末，約行 370）註冊：
   ```python
   _HANDLERS["my_compare"] = _check_my_compare
   ```
3. 在 `threshold.parse_threshold` 加新 `re.match` 分支，回傳 `compare_type="my_compare"` 的 dict。
4. 在 [`tests/test_checker.py`](../tests/test_checker.py) 新增測試類別（照抄 `TestCheckAbsolute` 或 `TestCheckPeriodChangePct` 結構）。
5. 在 [`tests/test_threshold.py`](../tests/test_threshold.py) 補新格式的解析測試。
6. 如果這個 `compare_type` 需要前前期（`Period_3`）資料，可能還要動 [`report._collect_needs_prev`](../src/risk_engine/report.py)（目前只判斷需不需要 `Period_2`）。

### 模板

```python
# checker.py
def _check_my_compare(
    current_val: float | None,
    prev_val: float | None,
    rule: dict[str, Any],
    report: types.Report | None = None,
) -> types.TagResult:
    # ... 你的判定邏輯
    return _tag_result(rule, status, threshold_str)


# 檔案末
_HANDLERS["my_compare"] = _check_my_compare
```

### 驗證

```bash
pytest tests/test_checker.py tests/test_threshold.py -v
```

---

## 3 新增段落

**會動到 [`combine_prompt.py`](../src/utils/combine_prompt.py) + 兩份 prompt 模板，最危險**。

例：要新增「股權結構」段落。

### 為什麼這個改動最危險？

整個系統把段落數寫死為五項，原因：

- [`SECTION_MAPPING`](../src/utils/combine_prompt.py)（行約 30）寫死 `{{risk_results_1}}` ~ `{{risk_results_5}}`。
- [`NARRATIVE_MAPPING`](../src/utils/combine_prompt.py)（行約 39）寫死 `{{narrative_1}}` ~ `{{narrative_5}}`。
- Prompt 模板（`risk_user_prompt.txt` / `narrative_user_prompt.txt`）寫死這些 placeholder。
- 規則 xlsx 的「財務分析指標」欄假設只能五擇一。

### 步驟

1. 決定新段落的編號（例：`{{risk_results_6}}` / `{{narrative_6}}`）。
2. 修改 [`combine_prompt.SECTION_MAPPING`](../src/utils/combine_prompt.py) 與 `NARRATIVE_MAPPING`，新增該段落。
3. 修改兩份 prompt 模板（`inputs/prompt/財報風險_user_prompt.txt`、`inputs/prompt/財報敘事_user_prompt.txt`），加上對應 placeholder。
4. 確認 EXE 同層也部署新版 prompt 模板。
5. 在 xlsx 兩個 sheet 新增該段落的列。
6. 跑全 pytest（不該破壞其他段落的測試）；新增段落層級的測試。

### 注意

- 改完之後**舊版 EXE 會無法跑新版 prompt 模板**（找不到舊段落 placeholder 會留下未替換的字串）。要做版本控制。
- 確認 [`build_grouped_narrative`](../src/utils/narrative.py) 會正確處理新段落。

---

## 4 meta-rule（多規則聯合觸發）

**目前只有預留接口在 [`post_rules.py`](../src/risk_engine/post_rules.py)**，沒有實作。

### 設計骨架（從 docstring 摘錄）

1. 定義 meta_rule 設定（在 indicators_config 同一份 JSON 或新增一個欄位）：
   ```json
   {
     "meta_id": "M001",
     "section": "綜合風險",
     "description": "...",
     "condition": {
       "node_type": "and",
       "children": [
         {"node_type": "tag_ref", "tag_id": "STRUCT_TAG1"},
         {"node_type": "tag_ref", "tag_id": "DEBT_TAG2"}
       ]
     }
   }
   ```
2. 在 [`checker.evaluate_node`](../src/risk_engine/checker.py) 加入 `node_type == "tag_ref"` 分支，從既有 `FullReport.sections` 找該 `tag_id` 的 status。
3. 實作 [`apply_post_rules(report_result, meta_rules)`](../src/risk_engine/post_rules.py)：跑 meta_rules 對每個 rule 呼叫 `evaluate_node`，把結果加進 `report_result.sections`（或新章節 `綜合風險`）。

### 待決定的設計問題

- 觸發的 meta-rule 應該獨立成一個段落，還是混進原段落？
- 是否要避免循環依賴（meta-rule 引用另一個 meta-rule）？
- LLM prompt 模板要不要對 meta-rule 開新 placeholder？

實作前要先寫 design doc 並確認 prompt 模板影響面。

---

## 5 通用注意事項

- **加測試**：新增任何 `compare_type` / 門檻格式都要在 `tests/` 補測試類別，遵循 [tests/README.md](../tests/README.md) 的命名與 fixture 慣例。
- **不要改 `_safe_eval`**：要新運算子請走 `_tokenize` → `_Parser`。
- **None 傳播不可破壞**：新 handler 必須處理 `current_val is None` / `prev_val is None` 的情況，回 `missing`。
- **更新文件**：改完後要同步：
  - [04_spec.md](04_spec.md) 中的型態 / 門檻 / 段落表
  - [README.md](../README.md) 對應章節
  - 如果有新例外，更新 [`types.py`](../src/risk_engine/types.py)

---

## 下一步

- 跑測試 / 看 log / 找錯 → [10_testing_and_debugging.md](10_testing_and_debugging.md)

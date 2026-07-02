# 02 Quickstart：30 分鐘上手

目標：跑通測試 → 跑通一次 legacy CLI → 看懂結果 JSON。完成後你能修改規則並驗證。

## 前置需求

- Python 3.10+
- 此專案根目錄（`/Users/kee/Documents/00_CODE/Taishin/risk_engine/` 在本地端）

---

## Step 1：安裝（2 min）

```bash
pip install -e .
```

`pyproject.toml` 設定 `pythonpath = ["src"]`，pytest 與 `pip install -e .` 都從 `src/` 解析 `risk_engine` 與 `utils` 套件。**import 時不要加 `src.` 前綴**。

---

## Step 2：跑測試（5 min）

```bash
pytest
```

預期看到 92 個測試通過。

挑一個你感興趣的模組單獨跑：

```bash
pytest tests/test_formula.py                            # 公式求值
pytest tests/test_threshold.py                          # 中文門檻解析
pytest tests/test_checker.py::TestCheckCompound         # 複合條件
pytest tests/test_pipeline.py                           # Pipeline
pytest --cov=risk_engine --cov=utils                    # 覆蓋率
```

各測試檔涵蓋的模組見 [tests/README.md](../tests/README.md)。

---

## Step 3：跑一次 legacy CLI（5 min）

Legacy CLI 是 debug 用的最快入口，不需要四份 HTML，只要一份 JSON 財報 + 一份 JSON indicator config：

```bash
python scripts/risk_checker.py \
    --report inputs/json_sample/sample_report.json \
    --config inputs/archive/indicators_config.json \
    --industry 7大指標 \
    --customer A00001 --date 20241231 \
    -o /tmp/result.json
```

打開 `/tmp/result.json`，你會看到 [04_spec.md#風險判定結果](04_spec.md#43-風險判定結果fullreport) 描述的 `FullReport` 結構。

加 `--debug` 看 DEBUG log：

```bash
python scripts/risk_checker.py --report ... --config ... --industry 7大指標 --debug
```

---

## Step 4：跑一次 EXE 流程（5 min，選做）

EXE 流程需要四份 HTML 與一份 xlsx。如果你還沒有 HTML 樣本，跳過這步。

```bash
python scripts/main.py f1.html f2.html f3.html f4.html \
    --industry 7大指標 \
    --xlsx inputs/indicators/20260507_7大關鍵指標.xlsx \
    --customer A00001 --date 20241231 \
    -o /tmp/exe.json
```

stdin JSON 模式（後端整合）：

```bash
echo '{"html_files":["f1.html","f2.html","f3.html","f4.html"],
       "industry":"7大指標"}' \
    | python scripts/main.py --stdin --stdout
```

---

## Step 5：看懂結果（10 min）

開兩份範例對照看：

| 檔案 | 角色 |
|------|------|
| [inputs/json_sample/risk_sample.json](../inputs/json_sample/risk_sample.json) | 完整 `FullReport` — 給 debug、CLI `-o` 輸出用 |
| [inputs/json_sample/risk_prompt_input_sample.json](../inputs/json_sample/risk_prompt_input_sample.json) | `to_prompt_view` 投影後的版本 — 真正送進 LLM |

對照「**固定長期適合率**」這條指標，注意兩份的差異：

```
原始 (risk_sample.json)               精簡 (risk_prompt_input_sample.json)
─────────────────────────             ────────────────────────────────────
indicator_code             ✗ 剝除
current_value              ✗ 剝除
current_display            ✓          current_display             ✓
operands[].code            ✗ 剝除
operands[].value           ✗ 剝除
operands[].period          ✓ 改名     period (= 原 period_label)   ✓
operands[].display         ✓          display                       ✓
taggings[].tag_id          ✗ 剝除
taggings[].threshold       ✓ 觸發才留
```

**為什麼要這樣剝除？** 不要把財報代碼（如 `TIBA040`）與原始浮點數送進 LLM，否則模型會把代碼當自然語言、或在敘述中重新換算數值。詳細對照表見專案根 [README.md#prompt-精簡視圖to_prompt_view](../README.md#prompt-精簡視圖to_prompt_view)。

---

## 你現在可以做什麼

- **修改規則**：打開 `inputs/indicators/20260507_7大關鍵指標.xlsx` 的「指標」sheet，新增一列。語法見 [08_config_authoring.md](08_config_authoring.md)。
- **驗證**：`pytest && python scripts/risk_checker.py --debug ...`
- **看原始碼**：[src/risk_engine/pipeline.py](../src/risk_engine/pipeline.py) 是雙分支 Pipeline 的入口，建議從這裡讀。

---

## 下一步

→ [03_architecture.md](03_architecture.md) 了解雙分支 Pipeline 為什麼這樣設計。

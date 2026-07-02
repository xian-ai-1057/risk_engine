# risk_engine 文件導覽

本資料夾是**新人導向**的補充文件。專案根 [README.md](../README.md) 仍是權威 spec；本資料夾的角色是把 30 KB 的 README 重新組織成「先讀什麼、再讀什麼」的閱讀路徑，並在新人需要 deep-dive 時連回原始章節。

---

## 30 分鐘上手路徑

| 順序 | 文件 | 你會學到 | 預估時間 |
|------|------|----------|---------|
| 1 | [01_overview.md](01_overview.md) | 這個系統的輸入是什麼、輸出是什麼、適用場景。 | 5 min |
| 2 | [02_quickstart.md](02_quickstart.md) | 安裝、跑通 `pytest`、跑通一次 legacy CLI、看懂結果 JSON。 | 15 min |
| 3 | [03_architecture.md](03_architecture.md) | 雙分支 Pipeline 全景、為什麼這樣分層、模組階層。 | 10 min |

完成上面三步後，你可以：
- 修改 `inputs/indicators/20260507_7大關鍵指標.xlsx` 新增一條規則
- 用 `python scripts/risk_checker.py --debug` 驗證
- 看懂 `inputs/json_sample/risk_sample.json` 中的「固定長期適合率」如何被剝離成 `inputs/json_sample/risk_prompt_input_sample.json`

---

## 進階查閱

| 何時打開 | 文件 |
|----------|------|
| 想知道某個欄位 / 例外 / 規則的正式定義 | [04_spec.md](04_spec.md) |
| 想搞清楚某條呼叫鏈（CLI / EXE / Pipeline 三條路徑） | [05_function_flow.md](05_function_flow.md) |
| 想搞清楚資料型別怎麼轉換（CSV → Report → FullReport → ExeOutput） | [06_data_flow.md](06_data_flow.md) |
| 在某個模組裡找特定函式 | [07_module_reference.md](07_module_reference.md) |

## 動手做事時

| 何時打開 | 文件 |
|----------|------|
| 要新增 / 修改指標規則 | [08_config_authoring.md](08_config_authoring.md) |
| 要擴充比較類型、門檻語法、段落、meta-rule | [09_extending.md](09_extending.md) |
| 跑測試 / 看 log / 找錯 | [10_testing_and_debugging.md](10_testing_and_debugging.md) |

---

## 這份文件**不**做的事

- **不重寫 spec**：正式定義都在 [README.md](../README.md)、[src/risk_engine/types.py](../src/risk_engine/types.py)，本資料夾遇到正式定義一律連回。
- **不取代 [CLAUDE.md](../CLAUDE.md)**：那份檔案是 Claude Code 的操作手冊，記錄專案最關鍵的非直覺慣例，內容已最佳化。
- **不取代 [tests/README.md](../tests/README.md)** 與 [AGENTS.md](../AGENTS.md)：測試組成與 agent 慣例請看原檔。

---

## 文件維護

- 程式檔行號可能漂移，請優先看「函式名稱」。
- 修改規則格式 / 新增段落 / 新增 `compare_type` 時，至少要同步：
  1. 本資料夾 [04_spec.md](04_spec.md)、[09_extending.md](09_extending.md)
  2. 專案根 [README.md](../README.md) 對應章節
  3. [src/risk_engine/types.py](../src/risk_engine/types.py) 型別定義

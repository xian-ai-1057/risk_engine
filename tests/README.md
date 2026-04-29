# 測試說明

## 概述

本專案使用 [pytest](https://docs.pytest.org/) 作為測試框架，目前共有 **92 個單元測試**，涵蓋 `risk_engine` 的四個核心模組。

測試設定定義於 `pyproject.toml`：

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-v --tb=short"
```

---

## 執行方式

```bash
# 執行所有測試
pytest

# 執行單一測試檔案
pytest tests/test_formula.py

# 執行特定測試類別
pytest tests/test_checker.py::TestCheckCompound

# 執行特定測試函式
pytest tests/test_formula.py::TestSafeEval::test_division_by_zero

# 顯示覆蓋率報告
pytest --cov=risk_engine --cov=utils

# 產出 HTML 覆蓋率報告
pytest --cov=risk_engine --cov=utils --cov-report=html
```

---

## 測試檔案說明

### `test_formula.py`（34 tests）

測試對象：`risk_engine/formula.py` — 公式求值模組（安全四則運算）

| 測試類別 | 測試數 | 說明 |
|----------|--------|------|
| `TestExtractCodes` | 7 | 從公式提取財報代碼，驗證 `_PRV`/`_PRV2` 後綴去除、去重、含括號公式 |
| `TestResolveCode` | 3 | 代碼後綴解析，驗證無後綴/`_PRV`/`_PRV2` 對應正確期別 |
| `TestTokenize` | 5 | 運算式 tokenizer，驗證數值/運算子/括號切割、非法字元拒絕 |
| `TestSafeEval` | 11 | 安全四則運算求值，涵蓋加減乘除、巢狀括號、負數、除以零、無效運算式 |
| `TestEvaluateFormula` | 8 | 完整公式求值，驗證從財報取值、跨期計算、缺失代碼/缺值處理 |

### `test_threshold.py`（16 tests）

測試對象：`risk_engine/threshold.py` — 中文門檻值解析模組

| 測試類別 | 測試數 | 說明 |
|----------|--------|------|
| `TestAbsoluteThreshold` | 5 | 絕對門檻解析：`>150%`、`<0`、`>=30`、`<=180天`、負值門檻 |
| `TestPeriodChangeThreshold` | 4 | 前期比較解析：比率增減百分比、絕對值增減天數 |
| `TestCompoundThreshold` | 3 | 複合條件（AND/OR）解析：樹狀結構建構、children 數值正確性 |
| `TestFullwidthNormalization` | 2 | 全形符號正規化：`＞` → `>`、`＜＝` → `<=` |
| `TestUnknownThreshold` | 2 | 無法解析的門檻回傳 `unknown`、多行取首行 |

### `test_checker.py`（25 tests）

測試對象：`risk_engine/checker.py` — 門檻比較模組（策略分派 + 遞迴求值）

| 測試類別 | 測試數 | 說明 |
|----------|--------|------|
| `TestCheckAbsolute` | 5 | 絕對門檻比較：triggered/not_triggered/missing、`>=`、`<` |
| `TestCheckPeriodChangePct` | 5 | 前期百分比變動：觸發/未觸發/缺前期/方向錯誤/decrease |
| `TestCheckPeriodChangeAbs` | 2 | 前期絕對值變動：觸發/未觸發 |
| `TestCheckCompound` | 4 | 複合條件：AND 全真/AND 一假/OR 一真/缺報表 |
| `TestCheckUnknownType` | 1 | 不支援的 compare_type 回傳 missing |
| `TestEvaluateNode` | 3 | 遞迴樹求值：葉節點 true/false/missing |
| `TestCalcPeriodChange` | 5 | 變動量計算：百分比增/減、前期為零、絕對值增/減 |

### `test_loader.py`（17 tests）

測試對象：`risk_engine/loader.py` — 資料載入模組

| 測試類別 | 測試數 | 說明 |
|----------|--------|------|
| `TestToFloat` | 8 | 數值轉換：None/int/float/string/空字串/空白/非數值/負數 |
| `TestLoadReportJson` | 3 | JSON 財報載入：正常載入/檔案不存在/無效 JSON |
| `TestLoadReportCsv` | 2 | CSV 財報載入：正常載入/缺少 key 欄位 |
| `TestLoadConfig` | 4 | 設定檔載入：正常載入/產業不存在/檔案不存在/無效 JSON |

---

## 新增測試指引

### 命名慣例

- 測試檔案：`test_<模組名>.py`
- 測試類別：`Test<功能描述>`（使用 PascalCase）
- 測試方法：`test_<行為描述>`（使用 snake_case）

### Fixture 使用

測試中使用 `@pytest.fixture()` 建立共用的測試資料：

```python
@pytest.fixture()
def sample_report(self):
    return {
        "TIBB011": {
            "FA_CANME": "應收帳款週轉天數",
            "單位": "天",
            "Current": 58.72,
            "Period_2": 47.9,
            "Period_3": 73.53,
        },
    }
```

檔案載入測試使用 pytest 內建的 `tmp_path` fixture 建立臨時檔案。

### 新增測試步驟

1. 在 `tests/` 目錄下建立或編輯對應的 `test_<模組名>.py`
2. 撰寫測試類別與方法
3. 執行 `pytest tests/test_<模組名>.py -v` 驗證
4. 確認所有測試通過後提交

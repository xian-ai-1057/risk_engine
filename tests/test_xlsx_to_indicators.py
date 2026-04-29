"""utils.xlsx_to_indicators 模組單元測試。

需要 pandas + openpyxl；若環境無此依賴，整個檔案 skip。
"""
import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("openpyxl")

from utils import xlsx_to_indicators as xi


# ── 共用 fixtures ────────────────────────────────────

def _make_indicator_df():
    return pd.DataFrame([
        {
            "產業別": "7大指標",
            "財務分析指標": "財務結構",
            "指標名稱": "負債權益比",
            "指標對應財報欄位": "TIBB002",
            "指標編號": "TIBB002_TAG1",
            "指標判斷門檻值": ">150%",
            "風險情境": "負債比偏高",
            "結果單位": "%",
        },
        {
            "產業別": "7大指標\n批發業",
            "財務分析指標": "現金流量",
            "指標名稱": "營業活動淨現金流入",
            "指標對應財報欄位": "TIBC014",
            "指標編號": "TIBC014_TAG1",
            "指標判斷門檻值": "<0",
            "風險情境": "經營性現金流入為負",
            "結果單位": "仟元",
        },
    ])


def _make_filter_df():
    return pd.DataFrame([
        {
            "產業別": "7大指標",
            "段落": "財務結構",
            "會計科目": "非流動資產",
            "會計科目代碼": "TIBA009",
        },
        {
            "產業別": "7大指標",
            "段落": "財務結構",
            "會計科目": "權益總額",
            "會計科目代碼": "TIBA040",
        },
        {
            "產業別": "7大指標",
            "段落": "現金流量",
            "會計科目": "營業活動之淨現金流入(流出)",
            "會計科目代碼": "TIBC014",
        },
        # 重複，應被去重
        {
            "產業別": "7大指標",
            "段落": "財務結構",
            "會計科目": "非流動資產",
            "會計科目代碼": "TIBA009",
        },
    ])


@pytest.fixture
def xlsx_path(tmp_path):
    path = tmp_path / "indicators.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        _make_indicator_df().to_excel(
            w, sheet_name="指標", index=False,
        )
        _make_filter_df().to_excel(
            w, sheet_name="敘事指標", index=False,
        )
    return str(path)


@pytest.fixture
def xlsx_fallback_path(tmp_path):
    """使用 Sheet1 / Sheet2 fallback 名稱。"""
    path = tmp_path / "indicators_fallback.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        _make_indicator_df().to_excel(
            w, sheet_name="Sheet1", index=False,
        )
        _make_filter_df().to_excel(
            w, sheet_name="Sheet2", index=False,
        )
    return str(path)


# ── parse_indicator_sheet ───────────────────────────

class TestParseIndicatorSheet:
    def test_basic(self):
        df = _make_indicator_df()
        config = xi.parse_indicator_sheet(df)
        assert "7大指標" in config
        assert "批發業" in config
        assert len(config["7大指標"]) == 2
        assert len(config["批發業"]) == 1

    def test_rule_shape(self):
        df = _make_indicator_df()
        config = xi.parse_indicator_sheet(df)
        rule = config["7大指標"][0]
        assert rule["section"] == "財務結構"
        assert rule["tag_id"] == "TIBB002_TAG1"
        assert rule["compare_type"] == "absolute"
        assert rule["operator"] == ">"
        assert rule["threshold"] == 150.0

    def test_missing_column_raises(self):
        df = pd.DataFrame([{"產業別": "X"}])
        with pytest.raises(ValueError, match="缺少欄位"):
            xi.parse_indicator_sheet(df)


# ── parse_filter_sheet ──────────────────────────────

class TestParseFilterSheet:
    def test_basic(self):
        df = _make_filter_df()
        result = xi.parse_filter_sheet(df)
        assert "7大指標" in result
        assert "財務結構" in result["7大指標"]
        assert "現金流量" in result["7大指標"]

    def test_codes_dedup(self):
        df = _make_filter_df()
        result = xi.parse_filter_sheet(df)
        codes = [
            item["code"]
            for item in result["7大指標"]["財務結構"]
        ]
        assert codes == ["TIBA009", "TIBA040"]

    def test_code_name_pair(self):
        df = _make_filter_df()
        result = xi.parse_filter_sheet(df)
        item = result["7大指標"]["財務結構"][0]
        assert item == {
            "code": "TIBA009", "name": "非流動資產",
        }

    def test_multi_industry_split(self):
        df = pd.DataFrame([{
            "產業別": "A\nB",
            "段落": "財務結構",
            "會計科目": "X",
            "會計科目代碼": "TIBA009",
        }])
        result = xi.parse_filter_sheet(df)
        assert "A" in result and "B" in result

    def test_skip_empty_rows(self):
        df = pd.DataFrame([{
            "產業別": "",
            "段落": "財務結構",
            "會計科目": "X",
            "會計科目代碼": "TIBA009",
        }])
        result = xi.parse_filter_sheet(df)
        assert result == {}

    def test_missing_column_raises(self):
        df = pd.DataFrame([{"產業別": "X"}])
        with pytest.raises(ValueError, match="缺少欄位"):
            xi.parse_filter_sheet(df)


# ── convert (end-to-end) ────────────────────────────

class TestConvertEndToEnd:
    def test_default_sheets(self, xlsx_path):
        config, nf = xi.convert(xlsx_path)
        assert "7大指標" in config
        assert "7大指標" in nf
        assert (
            len(nf["7大指標"]["財務結構"]) == 2
        )

    def test_fallback_sheets(self, xlsx_fallback_path):
        config, nf = xi.convert(xlsx_fallback_path)
        assert "7大指標" in config
        assert "7大指標" in nf

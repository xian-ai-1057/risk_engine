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
        keys = [
            item["key"]
            for item in result["7大指標"]["財務結構"]
        ]
        assert keys == ["TIBA009", "TIBA040"]

    def test_item_shape_legacy_columns_only(self):
        """S1.1：只給 4 必填欄位 → fallback 行為。"""
        df = _make_filter_df()
        result = xi.parse_filter_sheet(df)
        item = result["7大指標"]["財務結構"][0]
        assert item == {
            "key": "TIBA009",
            "display_name": "非流動資產",
            "expression": "TIBA009",
            "unit": "",
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

    # ── 新 schema 行為（S1.1〜S1.4） ────────────────

    def test_filter_with_formula_column(self):
        """S1.3：填 公式 → expression 透傳，key 仍取 code。"""
        df = pd.DataFrame([{
            "產業別": "7大指標",
            "段落": "財務結構",
            "會計科目": "(銀行借款+短期票券+公司債)/權益總額",
            "會計科目代碼": "TIBB004",
            "公式": "TIBB004*TIBA040/100",
            "顯示名稱": "銀行借款+短期票券+公司債",
            "單位": "仟元",
        }])
        result = xi.parse_filter_sheet(df)
        item = result["7大指標"]["財務結構"][0]
        assert item == {
            "key": "TIBB004",
            "display_name": "銀行借款+短期票券+公司債",
            "expression": "TIBB004*TIBA040/100",
            "unit": "仟元",
        }

    def test_filter_unit_and_display_name_override(self):
        """S1.3：選填欄位填值時透傳到 item。"""
        df = pd.DataFrame([{
            "產業別": "7大指標",
            "段落": "財務結構",
            "會計科目": "權益總額",
            "會計科目代碼": "TIBA040",
            "公式": "",
            "顯示名稱": "自訂顯示名稱",
            "單位": "億元",
        }])
        result = xi.parse_filter_sheet(df)
        item = result["7大指標"]["財務結構"][0]
        assert item["display_name"] == "自訂顯示名稱"
        assert item["unit"] == "億元"
        assert item["expression"] == "TIBA040"  # 公式留白 fallback

    def test_filter_key_collision_appends_suffix(self):
        """S1.3：同段落同 code 不同 expression → key 加後綴。"""
        df = pd.DataFrame([
            {
                "產業別": "7大指標",
                "段落": "償債能力",
                "會計科目": "速動比率",
                "會計科目代碼": "TIBB011",
                "公式": "",
                "顯示名稱": "",
                "單位": "",
            },
            {
                "產業別": "7大指標",
                "段落": "償債能力",
                "會計科目": "速動比率變動",
                "會計科目代碼": "TIBB011",
                "公式": "TIBB011-TIBB011_PRV",
                "顯示名稱": "速動比率變動量",
                "單位": "%",
            },
            {
                "產業別": "7大指標",
                "段落": "償債能力",
                "會計科目": "另一個變動",
                "會計科目代碼": "TIBB011",
                "公式": "TIBB011*2",
                "顯示名稱": "兩倍速動比率",
                "單位": "%",
            },
        ])
        result = xi.parse_filter_sheet(df)
        items = result["7大指標"]["償債能力"]
        keys = [i["key"] for i in items]
        assert keys == ["TIBB011", "TIBB011_2", "TIBB011_3"]
        assert items[1]["expression"] == "TIBB011-TIBB011_PRV"
        assert items[2]["expression"] == "TIBB011*2"

    def test_filter_dedup_exact_duplicate(self):
        """S1.4：完全重複的 (code, expression) 略過。"""
        df = pd.DataFrame([
            {
                "產業別": "7大指標", "段落": "財務結構",
                "會計科目": "權益總額", "會計科目代碼": "TIBA040",
                "公式": "", "顯示名稱": "", "單位": "",
            },
            {
                "產業別": "7大指標", "段落": "財務結構",
                "會計科目": "權益總額", "會計科目代碼": "TIBA040",
                "公式": "", "顯示名稱": "", "單位": "",
            },
        ])
        result = xi.parse_filter_sheet(df)
        assert len(result["7大指標"]["財務結構"]) == 1


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

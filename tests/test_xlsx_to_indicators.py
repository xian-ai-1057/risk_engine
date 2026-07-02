"""utils.xlsx_to_indicators 模組單元測試。

模組本體只用 openpyxl，但測試 fixture 用 pandas 來寫
xlsx（``pd.ExcelWriter``）比較簡便；若 dev 環境沒裝 pandas
就整檔 skip。``parse_indicator_sheet`` / ``parse_filter_sheet``
吃 (columns, rows) tuple，測試以 ``_sheet`` helper 構造。
"""
import pytest

pd = pytest.importorskip("pandas")
pytest.importorskip("openpyxl")

from utils import xlsx_to_indicators as xi


# ── 共用 fixtures ────────────────────────────────────

def _sheet(rows: list[dict]) -> tuple[list[str], list[dict[str, str]]]:
    """list[dict] → (columns, rows) Sheet tuple。

    模擬 ``_load_sheet`` 的回傳：所有 row 都補齊全 columns（空格 ""），
    cell 一律轉成 stripped str。columns 取自所有 row 的 key 聯集，
    保留首次出現順序。
    """
    columns: list[str] = []
    for r in rows:
        for k in r.keys():
            if k not in columns:
                columns.append(k)
    normalized: list[dict[str, str]] = []
    for r in rows:
        d = {c: "" for c in columns}
        for k, v in r.items():
            d[k] = "" if v is None else str(v).strip()
        normalized.append(d)
    return columns, normalized


def _make_indicator_rows():
    return [
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
    ]


def _make_filter_rows():
    return [
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
    ]


@pytest.fixture
def xlsx_path(tmp_path):
    path = tmp_path / "indicators.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        pd.DataFrame(_make_indicator_rows()).to_excel(
            w, sheet_name="指標", index=False,
        )
        pd.DataFrame(_make_filter_rows()).to_excel(
            w, sheet_name="敘事", index=False,
        )
    return str(path)


@pytest.fixture
def xlsx_fallback_path(tmp_path):
    """使用 Sheet1 / Sheet2 fallback 名稱。"""
    path = tmp_path / "indicators_fallback.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        pd.DataFrame(_make_indicator_rows()).to_excel(
            w, sheet_name="Sheet1", index=False,
        )
        pd.DataFrame(_make_filter_rows()).to_excel(
            w, sheet_name="Sheet2", index=False,
        )
    return str(path)


# ── parse_indicator_sheet ───────────────────────────

class TestParseIndicatorSheet:
    def test_basic(self):
        sheet = _sheet(_make_indicator_rows())
        config = xi.parse_indicator_sheet(sheet)
        assert "7大指標" in config
        assert "批發業" in config
        assert len(config["7大指標"]) == 2
        assert len(config["批發業"]) == 1

    def test_rule_shape(self):
        sheet = _sheet(_make_indicator_rows())
        config = xi.parse_indicator_sheet(sheet)
        rule = config["7大指標"][0]
        assert rule["section"] == "財務結構"
        assert rule["tag_id"] == "TIBB002_TAG1"
        assert rule["compare_type"] == "absolute"
        assert rule["operator"] == ">"
        assert rule["threshold"] == 150.0

    def test_missing_column_raises(self):
        sheet = _sheet([{"產業別": "X"}])
        with pytest.raises(ValueError, match="缺少欄位"):
            xi.parse_indicator_sheet(sheet)


# ── parse_filter_sheet ──────────────────────────────

class TestParseFilterSheet:
    def test_basic(self):
        sheet = _sheet(_make_filter_rows())
        result = xi.parse_filter_sheet(sheet)
        assert "7大指標" in result
        assert "財務結構" in result["7大指標"]
        assert "現金流量" in result["7大指標"]

    def test_codes_dedup(self):
        sheet = _sheet(_make_filter_rows())
        result = xi.parse_filter_sheet(sheet)
        keys = [
            item["key"]
            for item in result["7大指標"]["財務結構"]
        ]
        assert keys == ["TIBA009", "TIBA040"]

    def test_item_shape_legacy_columns_only(self):
        """S1.1：只給 4 必填欄位 → fallback 行為。"""
        sheet = _sheet(_make_filter_rows())
        result = xi.parse_filter_sheet(sheet)
        item = result["7大指標"]["財務結構"][0]
        assert item == {
            "key": "TIBA009",
            "display_name": "非流動資產",
            "expression": "TIBA009",
            "unit": "",
        }

    def test_multi_industry_split(self):
        sheet = _sheet([{
            "產業別": "A\nB",
            "段落": "財務結構",
            "會計科目": "X",
            "會計科目代碼": "TIBA009",
        }])
        result = xi.parse_filter_sheet(sheet)
        assert "A" in result and "B" in result

    def test_skip_empty_rows(self):
        sheet = _sheet([{
            "產業別": "",
            "段落": "財務結構",
            "會計科目": "X",
            "會計科目代碼": "TIBA009",
        }])
        result = xi.parse_filter_sheet(sheet)
        assert result == {}

    def test_missing_column_raises(self):
        sheet = _sheet([{"產業別": "X"}])
        with pytest.raises(ValueError, match="缺少欄位"):
            xi.parse_filter_sheet(sheet)

    # ── 新 schema 行為（S1.1〜S1.4） ────────────────

    def test_filter_with_formula_column(self):
        """S1.3：填 公式 → expression 透傳，key 仍取 code。"""
        sheet = _sheet([{
            "產業別": "7大指標",
            "段落": "財務結構",
            "會計科目": "(銀行借款+短期票券+公司債)/權益總額",
            "會計科目代碼": "TIBB004",
            "公式": "TIBB004*TIBA040/100",
            "顯示名稱": "銀行借款+短期票券+公司債",
            "單位": "仟元",
        }])
        result = xi.parse_filter_sheet(sheet)
        item = result["7大指標"]["財務結構"][0]
        assert item == {
            "key": "TIBB004",
            "display_name": "銀行借款+短期票券+公司債",
            "expression": "TIBB004*TIBA040/100",
            "unit": "仟元",
        }

    def test_filter_unit_and_display_name_override(self):
        """S1.3：選填欄位填值時透傳到 item。"""
        sheet = _sheet([{
            "產業別": "7大指標",
            "段落": "財務結構",
            "會計科目": "權益總額",
            "會計科目代碼": "TIBA040",
            "公式": "",
            "顯示名稱": "自訂顯示名稱",
            "單位": "億元",
        }])
        result = xi.parse_filter_sheet(sheet)
        item = result["7大指標"]["財務結構"][0]
        assert item["display_name"] == "自訂顯示名稱"
        assert item["unit"] == "億元"
        assert item["expression"] == "TIBA040"  # 公式留白 fallback

    def test_filter_display_absolute_truthy(self):
        """選填「顯示為絕對值」=「是」→ entry 帶 display_absolute=True。"""
        sheet = _sheet([{
            "產業別": "7大指標",
            "段落": "現金流量",
            "會計科目": "發放現金股利",
            "會計科目代碼": "TIBC027",
            "顯示為絕對值": "是",
        }])
        result = xi.parse_filter_sheet(sheet)
        item = result["7大指標"]["現金流量"][0]
        assert item["display_absolute"] is True

    def test_filter_display_absolute_blank_omitted(self):
        """空白 / 缺欄 → entry 不寫 display_absolute key。"""
        sheet = _sheet([{
            "產業別": "7大指標",
            "段落": "現金流量",
            "會計科目": "其他",
            "會計科目代碼": "TIBC099",
            "顯示為絕對值": "",
        }])
        result = xi.parse_filter_sheet(sheet)
        item = result["7大指標"]["現金流量"][0]
        assert "display_absolute" not in item

    def test_filter_display_absolute_other_truthy_aliases(self):
        """y / true / 1 同樣視為 True。"""
        sheet = _sheet([
            {
                "產業別": "7大指標",
                "段落": "現金流量",
                "會計科目": "A",
                "會計科目代碼": "C1",
                "顯示為絕對值": "Y",
            },
            {
                "產業別": "7大指標",
                "段落": "現金流量",
                "會計科目": "B",
                "會計科目代碼": "C2",
                "顯示為絕對值": "TRUE",
            },
            {
                "產業別": "7大指標",
                "段落": "現金流量",
                "會計科目": "C",
                "會計科目代碼": "C3",
                "顯示為絕對值": "1",
            },
        ])
        result = xi.parse_filter_sheet(sheet)
        items = result["7大指標"]["現金流量"]
        assert all(
            item["display_absolute"] is True
            for item in items
        )

    def test_filter_key_collision_appends_suffix(self):
        """S1.3：同段落同 code 不同 expression → key 加後綴。"""
        sheet = _sheet([
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
        result = xi.parse_filter_sheet(sheet)
        items = result["7大指標"]["償債能力"]
        keys = [i["key"] for i in items]
        assert keys == ["TIBB011", "TIBB011_2", "TIBB011_3"]
        assert items[1]["expression"] == "TIBB011-TIBB011_PRV"
        assert items[2]["expression"] == "TIBB011*2"

    def test_filter_with_calc_formula_alias(self):
        """新版欄位名 計算公式 也視為公式來源。"""
        sheet = _sheet([{
            "產業別": "7大指標",
            "段落": "償債能力",
            "會計科目": "(銀行借款+短期票券+公司債)",
            "會計科目代碼": "TIBB004,TIBA040",
            "計算公式（中文表示）":
                "((銀行借款+短期票券+公司債)/權益總額)*權益總額",
            "計算公式": "TIBB004*TIBA040",
        }])
        result = xi.parse_filter_sheet(sheet)
        item = result["7大指標"]["償債能力"][0]
        assert item["expression"] == "TIBB004*TIBA040"
        assert item["key"] == "TIBB004,TIBA040"

    def test_replacement_unit_overrides_unit(self):
        """替換單位 填值時優先於 單位。

        例：((A+B+C)/D)*D 公式計算結果其實是 仟元（不是 %），
        以「替換單位」覆寫顯示單位。
        """
        sheet = _sheet([{
            "產業別": "7大指標",
            "段落": "財務結構",
            "會計科目": "(銀行借款+短期票券+公司債)",
            "會計科目代碼": "TIBB004",
            "計算公式": "TIBB004*TIBA040/100",
            "單位": "%",
            "替換單位": "仟元",
        }])
        result = xi.parse_filter_sheet(sheet)
        item = result["7大指標"]["財務結構"][0]
        assert item["unit"] == "仟元"

    def test_replacement_unit_blank_falls_back_to_unit(self):
        """替換單位 留白 → 維持原本 單位 行為。"""
        sheet = _sheet([{
            "產業別": "7大指標",
            "段落": "財務結構",
            "會計科目": "權益總額",
            "會計科目代碼": "TIBA040",
            "公式": "",
            "顯示名稱": "",
            "單位": "億元",
            "替換單位": "",
        }])
        result = xi.parse_filter_sheet(sheet)
        item = result["7大指標"]["財務結構"][0]
        assert item["unit"] == "億元"

    def test_replacement_unit_only(self):
        """只填 替換單位、不填 單位 → 用 替換單位。"""
        sheet = _sheet([{
            "產業別": "7大指標",
            "段落": "財務結構",
            "會計科目": "權益總額",
            "會計科目代碼": "TIBA040",
            "替換單位": "%",
        }])
        result = xi.parse_filter_sheet(sheet)
        item = result["7大指標"]["財務結構"][0]
        assert item["unit"] == "%"

    def test_parent_key_from_note(self):
        """備註『{父}子項目』→ 子項 entry 帶 parent_key。"""
        sheet = _sheet([
            {
                "產業別": "7大指標", "段落": "現金流量",
                "會計科目": "籌資活動之現金流入(流出)",
                "會計科目代碼": "TIBC033",
            },
            {
                "產業別": "7大指標", "段落": "現金流量",
                "會計科目": "現金增(減)資",
                "會計科目代碼": "TIBC029",
                "備註": "籌資活動之現金流入(流出)子項目",
            },
            {
                "產業別": "7大指標", "段落": "現金流量",
                "會計科目": "發放現金股利",
                "會計科目代碼": "TIBC027",
                "備註": "籌資活動之現金流入(流出)子項目",
            },
        ])
        result = xi.parse_filter_sheet(sheet)
        items = {
            item["key"]: item
            for item in result["7大指標"]["現金流量"]
        }
        assert "parent_key" not in items["TIBC033"]
        assert items["TIBC029"]["parent_key"] == "TIBC033"
        assert items["TIBC027"]["parent_key"] == "TIBC033"

    def test_parent_key_child_before_parent(self):
        """父項在子項之後出現也能解析（兩階段索引）。"""
        sheet = _sheet([
            {
                "產業別": "7大指標", "段落": "現金流量",
                "會計科目": "現金增(減)資",
                "會計科目代碼": "TIBC029",
                "備註": "籌資活動之現金流入(流出)子項目",
            },
            {
                "產業別": "7大指標", "段落": "現金流量",
                "會計科目": "籌資活動之現金流入(流出)",
                "會計科目代碼": "TIBC033",
            },
        ])
        result = xi.parse_filter_sheet(sheet)
        items = {
            item["key"]: item
            for item in result["7大指標"]["現金流量"]
        }
        assert items["TIBC029"]["parent_key"] == "TIBC033"

    def test_parent_key_unknown_parent_warns(self, caplog):
        """備註符合 pattern 但同段落沒有對應父項 → warning + 平項。"""
        sheet = _sheet([
            {
                "產業別": "7大指標", "段落": "現金流量",
                "會計科目": "現金增(減)資",
                "會計科目代碼": "TIBC029",
                "備註": "不存在的父項子項目",
            },
        ])
        with caplog.at_level("WARNING"):
            result = xi.parse_filter_sheet(sheet)
        item = result["7大指標"]["現金流量"][0]
        assert "parent_key" not in item
        assert any(
            "找不到父項" in rec.message
            for rec in caplog.records
        )

    def test_parent_key_note_pattern_mismatch_ignored(self):
        """備註不以『子項目』結尾 → 忽略、無 parent_key。"""
        sheet = _sheet([
            {
                "產業別": "7大指標", "段落": "現金流量",
                "會計科目": "現金增(減)資",
                "會計科目代碼": "TIBC029",
                "備註": "這只是說明文字",
            },
        ])
        result = xi.parse_filter_sheet(sheet)
        item = result["7大指標"]["現金流量"][0]
        assert "parent_key" not in item

    def test_parent_key_scoped_to_section(self):
        """父項查找限縮於同產業同段落內，跨段落不會誤抓。"""
        sheet = _sheet([
            {
                "產業別": "7大指標", "段落": "財務結構",
                "會計科目": "籌資活動之現金流入(流出)",
                "會計科目代碼": "TIBC033",
            },
            {
                "產業別": "7大指標", "段落": "現金流量",
                "會計科目": "現金增(減)資",
                "會計科目代碼": "TIBC029",
                "備註": "籌資活動之現金流入(流出)子項目",
            },
        ])
        result = xi.parse_filter_sheet(sheet)
        item = result["7大指標"]["現金流量"][0]
        assert "parent_key" not in item

    def test_filter_dedup_exact_duplicate(self):
        """S1.4：完全重複的 (code, expression) 略過。"""
        sheet = _sheet([
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
        result = xi.parse_filter_sheet(sheet)
        assert len(result["7大指標"]["財務結構"]) == 1


# ── convert (end-to-end) ────────────────────────────

class TestConvertEndToEnd:
    def test_default_sheets(self, xlsx_path):
        config, nf, tag_map = xi.convert(xlsx_path)
        assert "7大指標" in config
        assert "7大指標" in nf
        assert (
            len(nf["7大指標"]["財務結構"]) == 2
        )
        # 此 fixture 不包含 tag_table sheet → 空 dict
        assert tag_map == {}

    def test_fallback_sheets(self, xlsx_fallback_path):
        config, nf, tag_map = xi.convert(xlsx_fallback_path)
        assert "7大指標" in config
        assert "7大指標" in nf
        assert tag_map == {}


# ── parse_tag_table_sheet ───────────────────────────

def _make_tag_table_rows():
    return [
        {"FA_RFNBR": "TIBA001", "FA_CANME": "流動資產", "單位": "仟元"},
        {"FA_RFNBR": "TIBA002", "FA_CANME": "現金及約當現金", "單位": "仟元"},
        {"FA_RFNBR": "TIBA015", "FA_CANME": "資產總額", "單位": "仟元"},
    ]


@pytest.fixture
def xlsx_with_tag_table(tmp_path):
    """指標 + 敘事 + tag_table 三張 sheet。"""
    path = tmp_path / "indicators_with_tags.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as w:
        pd.DataFrame(_make_indicator_rows()).to_excel(
            w, sheet_name="指標", index=False,
        )
        pd.DataFrame(_make_filter_rows()).to_excel(
            w, sheet_name="敘事", index=False,
        )
        pd.DataFrame(_make_tag_table_rows()).to_excel(
            w, sheet_name="tag_table", index=False,
        )
    return str(path)


class TestParseTagTableSheet:
    def test_basic(self, xlsx_with_tag_table):
        tag_map = xi.parse_tag_table_sheet(xlsx_with_tag_table)
        assert tag_map == {
            "TIBA001": "流動資產",
            "TIBA002": "現金及約當現金",
            "TIBA015": "資產總額",
        }

    def test_missing_sheet_returns_empty(self, xlsx_path):
        """xlsx 沒有 tag_table sheet → 回空 dict，不拋錯。"""
        tag_map = xi.parse_tag_table_sheet(xlsx_path)
        assert tag_map == {}

    def test_missing_column_raises(self, tmp_path):
        path = tmp_path / "bad_tags.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as w:
            pd.DataFrame([
                {"FA_RFNBR": "TIBA001"},
            ]).to_excel(w, sheet_name="tag_table", index=False)
        with pytest.raises(ValueError, match="缺少欄位"):
            xi.parse_tag_table_sheet(str(path))

    def test_skip_blank_rows(self, tmp_path):
        path = tmp_path / "blank_tags.xlsx"
        with pd.ExcelWriter(path, engine="openpyxl") as w:
            pd.DataFrame([
                {"FA_RFNBR": "TIBA001", "FA_CANME": "流動資產"},
                {"FA_RFNBR": "", "FA_CANME": "孤兒名稱"},
                {"FA_RFNBR": "TIBA002", "FA_CANME": ""},
            ]).to_excel(w, sheet_name="tag_table", index=False)
        tag_map = xi.parse_tag_table_sheet(str(path))
        assert tag_map == {"TIBA001": "流動資產"}

    def test_convert_includes_tag_map(self, xlsx_with_tag_table):
        """convert() end-to-end 也應把 tag_map 帶出來。"""
        _config, _nf, tag_map = xi.convert(xlsx_with_tag_table)
        assert tag_map["TIBA001"] == "流動資產"

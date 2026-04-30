"""報表處理 Pipeline（risk / narrative 雙獨立分支）。

從財報出發，分兩條互不依賴的管線：
  - Risk 分支：indicator.json (rules) → 計算指標 → 分組 sections
  - Narrative 分支：narrative_filter.json → 撈報表 → 分組 codes

最後在 prompt renderer 各自填入對應 placeholder。

用法:
    from risk_engine import loader
    from risk_engine.pipeline import ReportPipeline
    from utils.narrative import load_narrative_filter

    report = loader.load_report("report.json")
    rules  = loader.load_config("indicator.json", "批發業")
    narrative_filter = load_narrative_filter(
        "narrative_filter.json", "批發業",
    )

    pipe = ReportPipeline(
        report=report,
        rules=rules,
        narrative_filter=narrative_filter,
        narrative_prompt_template=narr_text,
        risk_prompt_template=risk_text,
    )
    result = pipe.run()
"""
import logging
from collections import OrderedDict
from typing import Any

from risk_engine import types
from risk_engine import report as report_mod
from risk_engine import post_rules
from utils.narrative import build_grouped_narrative
from utils.combine_prompt import (
    render_narrative_prompt,
    render_risk_prompt,
)

logger = logging.getLogger(__name__)


class ReportPipeline:
    """報表處理 Pipeline。

    Args:
        report: 完整財報資料。
        rules: 該產業的指標規則列表。
        narrative_prompt_template: 敘事 Prompt 模板文字。
        risk_prompt_template: 風險 Prompt 模板文字。
        narrative_filter: 該產業的敘事過濾
            ({section: [{code, name}, ...]})。未提供則
            不產出 narrative 內容。
        customer_id: 客戶代碼（風險報告用）。
        report_date: 報表日期（風險報告用）。
        industry: 產業別（風險報告用）。
    """

    def __init__(
        self,
        report: types.Report,
        rules: list[dict[str, Any]],
        narrative_prompt_template: str,
        risk_prompt_template: str,
        narrative_filter: dict[
            str, list[dict[str, str]]
        ] | None = None,
        customer_id: str = "",
        report_date: str = "",
        industry: str = "",
        period_dates: list[str] | None = None,
    ) -> None:
        self._report = report
        self._rules = rules
        self._narrative_template = narrative_prompt_template
        self._risk_template = risk_prompt_template
        self._narrative_filter = narrative_filter
        self._customer_id = customer_id
        self._report_date = report_date
        self._industry = industry
        self._period_dates = period_dates

    # ── Step 1: 過濾 & 分群（filter-driven） ────────

    def filter_and_group(
        self,
    ) -> types.GroupedReport:
        """根據 narrative_filter 撈報表並依段落分群。

        純 filter-driven，不從指標公式抽 codes。
        若未提供 narrative_filter，回空 dict。

        Returns:
            {章節名: {代碼: ReportRow}} 結構。
        """
        if not self._narrative_filter:
            logger.info(
                "未提供 narrative_filter，"
                "filter_and_group 回空 dict",
            )
            return OrderedDict()

        logger.info("開始 filter-driven 分群")
        return build_grouped_narrative(
            self._report, self._narrative_filter,
        )

    # ── Step 2a: 敘事 Prompt 合併（部分一）──────────

    def build_narrative_prompt(
        self,
        grouped: types.GroupedReport,
    ) -> str:
        """將分群後的原始報表 JSON 填入敘事 Prompt。

        若 ``__init__`` 帶入 ``period_dates``，會在此處
        交由 ``render_narrative_prompt`` 進一步格式化日期。

        Args:
            grouped: filter_and_group() 的輸出。

        Returns:
            合併後的敘事 Prompt 字串。
        """
        logger.info("開始建構敘事 Prompt")
        return render_narrative_prompt(
            self._narrative_template,
            grouped,
            period_dates=self._period_dates,
        )

    # ── Step 2b: 風險判定 + Prompt 合併（部分二）────

    def build_risk_prompt(
        self,
    ) -> tuple[types.FullReport, str]:
        """對完整報表執行風險判定並合併風險 Prompt。

        1. 以完整報表執行風險判定
        2. 將結果填入風險 Prompt 模板

        Returns:
            (風險判定 FullReport, 合併後風險 Prompt)。
        """
        logger.info("開始風險判定")

        risk_report = report_mod.generate_report(
            self._report,
            self._rules,
            self._customer_id,
            self._report_date,
            self._industry,
        )
        risk_report = post_rules.apply_post_rules(
            risk_report,
        )

        logger.info("開始合併風險 Prompt")
        risk_prompt = render_risk_prompt(
            self._risk_template, risk_report,
        )

        return risk_report, risk_prompt

    # ── 完整執行 ────────────────────────────────────

    def run(self) -> types.PipelineResult:
        """執行完整 Pipeline。

        流程:
          1. 過濾報表 + 按章節分群
          2a. 分群報表 → 敘事 Prompt 合併
          2b. 完整報表 → 風險判定 → 風險 Prompt 合併

        2a 與 2b 邏輯上互相獨立，此處以序列方式
        依次執行。

        Returns:
            PipelineResult 包含:
              narrative_prompt  合併後的敘事 Prompt
              risk_prompt       合併後的風險 Prompt
              grouped_report    過濾分群後的報表
              risk_report       風險判定結果
        """
        logger.info("Pipeline 啟動")

        # Step 1
        grouped = self.filter_and_group()

        # Step 2a: 敘事
        narrative_prompt = (
            self.build_narrative_prompt(grouped)
        )

        # Step 2b: 風險（使用完整報表，與 Step 2a 獨立）
        risk_report, risk_prompt = (
            self.build_risk_prompt()
        )

        logger.info("Pipeline 完成")
        return {
            "narrative_prompt": narrative_prompt,
            "risk_prompt": risk_prompt,
            "grouped_report": grouped,
            "risk_report": risk_report,
        }

"""risk_engine — 財報風險判斷引擎。

模組結構：
  types      型別定義（TypedDict）+ 自訂例外
  log_config 統一 logging 設定
  formula    公式求值（安全四則運算）
  threshold  門檻值解析（樹狀 compound）
  checker    門檻比較（策略分派 + 遞迴求值）
  loader     資料載入（財報 CSV/JSON / 設定 JSON）
  report     報告產生 + LLM 精簡格式
  post_rules 多規則聯合觸發（預留）

頂層模組：
  pipeline   報表處理 Pipeline（ReportPipeline）
"""
from risk_engine.formula import evaluate_formula
from risk_engine.threshold import parse_threshold
from risk_engine.checker import check_rule
from risk_engine.checker import evaluate_node
from risk_engine.loader import load_report
from risk_engine.loader import load_config
from risk_engine.loader import load_csv
from risk_engine.report import generate_report
from risk_engine.report import to_llm_format
from risk_engine.post_rules import apply_post_rules
from risk_engine.types import GroupedReport
from risk_engine.types import PipelineResult
from risk_engine.pipeline import ReportPipeline

__all__ = [
    "evaluate_formula",
    "parse_threshold",
    "check_rule",
    "evaluate_node",
    "load_report",
    "load_config",
    "load_csv",
    "generate_report",
    "to_llm_format",
    "apply_post_rules",
    "GroupedReport",
    "PipelineResult",
    "ReportPipeline",
]
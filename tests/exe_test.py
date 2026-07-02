"""Manual smoke script for the built EXE on Windows.

不是 pytest 測試，純粹是手動驗證腳本。預設路徑寫死指向開發機
的 deploy 目錄，請於執行前依實機調整。包在 ``__main__`` 內，
避免 pytest 蒐集時直接呼叫 subprocess（缺檔會造成 collection error）。

執行方式::

    python tests/exe_test.py
"""
import json
import subprocess
import sys


_EXE_PATH = (
    r"D:\02_專案\03_法金報告生成\01_Code"
    r"\risk_analyzer\V7\deploy\risk_analysis.exe"
)
_HTML_BASE = (
    r"D:\02_專案\03_法金報告生成\01_Code"
    r"\risk_analyzer\V7\data\html"
)


def main() -> int:
    payload = {
        "html_files": [
            rf"{_HTML_BASE}\財報_1財務概況.html",
            rf"{_HTML_BASE}\財報_2財務比率.html",
            rf"{_HTML_BASE}\財報_3現金流量.html",
            rf"{_HTML_BASE}\財報_4淨值調節.html",
        ],
        "xlsx": r"D:\02_專案\03_法金報告生成\01_Code\risk_analyzer\v7\deploy\20260506_7大關鍵指標.xlsx",
        "industry": "7大指標",
        "request_id": "test-exe-001",
    }

    result = subprocess.run(
        [_EXE_PATH, "--stdin", "--stdout"],
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        timeout=120,
    )

    print("return_code:", result.returncode)
    output = json.loads(result.stdout)
    print(json.dumps(output, ensure_ascii=False, indent=4))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())

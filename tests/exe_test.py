import json 
import subprocess

payload = {
    "html_files": [
        r"D:\02_專案\03_法金報告生成\01_Code\risk_analyzer\V6\data\html\財報_1財務概況.html",
        r"D:\02_專案\03_法金報告生成\01_Code\risk_analyzer\V6\data\html\財報_2財務比率.html",
        r"D:\02_專案\03_法金報告生成\01_Code\risk_analyzer\V6\data\html\財報_3現金流量.html",
        r"D:\02_專案\03_法金報告生成\01_Code\risk_analyzer\V6\data\html\財報_4淨值調節.html"
        ],
    "industry": "7大指標",
    "request_id": "test-exe-002"
}

result = subprocess.run(
    [r"D:\02_專案\03_法金報告生成\01_Code\risk_analyzer\V6\deploy\risk_analysis.exe", "--stdin", "--stdout"],
    input=json.dumps(payload, ensure_ascii=False),
    capture_output=True,
    text=True,
    timeout=120
)

print("return_code:", result.returncode)
output = json.loads(result.stdout)
print(json.dumps(output, ensure_ascii=False, indent=4))
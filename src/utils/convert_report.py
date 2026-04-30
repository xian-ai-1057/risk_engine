"""批次將資料夾中的 JSON 風險報告 TXT 轉換為段落格式。

從每個 TXT 檔案中擷取 JSON dict（即使外面包了其他文字），
轉換為帶章節標題的段落格式，輸出到指定資料夾。
"""

import json
import os
import re

# ====== 設定區（請依需求修改）======
INPUT_DIR = r"/home/jovyan/00_專案/報告生成/法金報告生成/02_Code/V4/DATA/output/v3"
OUTPUT_DIR = r"/home/jovyan/00_專案/報告生成/法金報告生成/02_Code/V4/DATA/output/v3/report"
# =====================================

# 章節標題對應
SECTION_TITLES = {
    "4-1": "財務結構",
    "4-2": "償債能力",
    "4-3": "經營效能",
    "4-4": "獲利能力",
    "4-5": "現金流量",
}


def extract_json_from_text(text: str) -> dict | None:
    """從可能夾雜其他文字的內容中擷取第一個 JSON dict。

    Args:
        text: 原始文字內容，JSON 可能被其他文字包圍。

    Returns:
        解析後的 dict，若找不到或解析失敗則回傳 None。
    """
    # 策略 1：嘗試直接解析整段文字
    try:
        data = json.loads(text.strip())
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    # 策略 2：用正則找出最外層的 { ... } 區塊
    matches = re.finditer(r"\{", text)
    for m in matches:
        start = m.start()
        # 從 { 開始，逐層計算括號配對
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            if depth == 0:
                candidate = text[start:i + 1]
                try:
                    data = json.loads(candidate)
                    if isinstance(data, dict):
                        return data
                except json.JSONDecodeError:
                    break
    return None


def convert_dict_to_paragraphs(data: dict) -> str:
    """將 dict 轉換為段落格式字串。

    Args:
        data: key 為 "4-1"~"4-5" 的報告內容 dict。

    Returns:
        帶章節標題的段落格式字串。
    """
    paragraphs = []
    for key in sorted(data.keys()):
        title = SECTION_TITLES.get(key, key)
        paragraphs.append(f"# {title}\n{data[key]}")
    return "\n\n".join(paragraphs) + "\n"


def batch_convert(input_dir: str, output_dir: str) -> None:
    """批次轉換資料夾中所有 TXT 檔案。

    Args:
        input_dir: 輸入資料夾路徑。
        output_dir: 輸出資料夾路徑。
    """
    os.makedirs(output_dir, exist_ok=True)

    txt_files = sorted(
        f for f in os.listdir(input_dir)
        if f.lower().endswith(".txt")
    )

    if not txt_files:
        print(f"[警告] 在 {input_dir} 中未找到任何 .txt 檔案")
        return

    success_count = 0
    fail_count = 0

    for filename in txt_files:
        input_path = os.path.join(input_dir, filename)
        output_path = os.path.join(output_dir, filename)

        with open(input_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        data = extract_json_from_text(raw_text)
        if data is None:
            print(f"[失敗] {filename} - 無法擷取 JSON")
            fail_count += 1
            continue

        result = convert_dict_to_paragraphs(data)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result)

        print(f"[完成] {filename}")
        success_count += 1

    print(f"\n處理完畢：成功 {success_count} 筆，"
          f"失敗 {fail_count} 筆")
    print(f"輸出位置：{os.path.abspath(output_dir)}")


def main() -> None:
    """主程式進入點。"""
    batch_convert(INPUT_DIR, OUTPUT_DIR)


if __name__ == "__main__":
    main()
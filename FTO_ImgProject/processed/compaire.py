import os
import pandas as pd
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# xlsx 파일에서 출원번호 읽기
excel_file = str(PROJECT_ROOT / "data/rawdata/1981-2026.xlsx")
df = pd.read_excel(excel_file, engine='openpyxl')

# 출원번호 추출
application_numbers = df.iloc[6:, 1].dropna().astype(str).str.strip().tolist()
xlsx_numbers_set = set(application_numbers)

print(f"📊 xlsx 파일의 출원번호 개수: {len(xlsx_numbers_set)}")

# 저장된 xml 파일명 읽기
xml_dir = str(PROJECT_ROOT / "data/api_xml")
xml_files = [f.replace('.xml', '') for f in os.listdir(xml_dir) if f.endswith('.xml')]
xml_numbers_set = set(xml_files)

print(f"📁 저장된 xml 파일 개수: {len(xml_numbers_set)}")

# xlsx에는 있지만 xml에는 없는 출원번호 찾기
missing_numbers = xlsx_numbers_set - xml_numbers_set

print(f"❌ 누락된 출원번호: {len(missing_numbers)}개")

# 누락된 출원번호를 txt 파일로 저장
if missing_numbers:
    log_dir = str(PROJECT_ROOT / "data/error_Flow/error_출원번호")
    os.makedirs(log_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    missing_file = f"{log_dir}/missing_applications_{timestamp}.txt"
    
    # 출원번호를 정렬해서 저장
    with open(missing_file, 'w', encoding='utf-8') as f:
        for num in sorted(missing_numbers):
            f.write(f"{num}\n")
    
    print(f"✅ 누락된 출원번호 목록 저장: {missing_file}")
else:
    print("✅ 모든 출원번호가 xml로 저장되었습니다!")
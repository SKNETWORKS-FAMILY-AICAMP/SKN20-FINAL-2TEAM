import os, time, requests, json
from dotenv import load_dotenv
from datetime import datetime
from openpyxl import load_workbook
import pandas as pd

# 파일의 스타일시트(XML)에 잘못된 색상 값이 포함되어 있어 openpyxl읽을 수 있게 pandas 이용.

load_dotenv()
API_KEY = os.getenv("KIPRISPLUS_API_KEY")
assert API_KEY, "KIPRISPLUS_API_KEY 없음 (.env 확인)"

# 출원번호 들어있는 엑셀 파일 로드
excel_file = r"/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/평가데이터/거절출원번호_유사이미지있음.xlsx"

# pandas로 엑셀 파일 읽기
df = pd.read_excel(excel_file, engine='openpyxl')

# 출원번호 추출 - B열은 인덱스 1, 헤더 제외하면 B1007 = iloc[1005]
application_numbers = df.iloc[7:, 1].dropna().astype(str).str.strip().tolist()


print(f"📊 {excel_file} 파일에서 {len(application_numbers)}개의 출원번호를 읽었습니다.\n")

# 서지상세정보 API 호출
base_url = "http://plus.kipris.or.kr/kipo-api/kipi/designInfoSearchService/getBibliographyDetailInfoSearch"

# 폴더 생성
output_dir = "/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/평가데이터/reject"
log_dir = "/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/평가데이터/reject_error"
os.makedirs(output_dir, exist_ok=True)
os.makedirs(log_dir, exist_ok=True)

success_count = 0
fail_count = 0
failed_items = []
errors_log = []

for idx, app_num in enumerate(application_numbers, 1):
    try:
        params = {
            "applicationNumber": app_num,
            "ServiceKey": API_KEY,
        }
        
        t0 = time.time()
        r = requests.get(base_url, params=params, timeout=20)
        latency_ms = int((time.time() - t0) * 1000)
        
        print(f"[{idx}/{len(application_numbers)}] {app_num} - status: {r.status_code}, latency: {latency_ms}ms")
        
        # XML 파일로 저장
        if r.status_code == 200:
            try:
                file_path = f"{output_dir}/{app_num}.xml"
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(r.text)
                print(f"         ✅ 저장: {file_path}")
                success_count += 1
            except IOError as io_err:
                error_msg = f"[파일 저장 오류] {app_num}: {type(io_err).__name__} - {str(io_err)}"
                print(f"         ❌ {error_msg}")
                fail_count += 1
                failed_items.append(app_num)
                errors_log.append(error_msg)
        else:
            error_msg = f"[API 응답 오류] {app_num}: Status Code {r.status_code}"
            print(f"         ❌ {error_msg}")
            fail_count += 1
            failed_items.append(app_num)
            errors_log.append(error_msg)
            
        time.sleep(0.9)
        
    except requests.exceptions.Timeout:
        error_msg = f"[타임아웃] {app_num}: 요청 시간 초과"
        print(f"[{idx}/{len(application_numbers)}] {app_num} - {error_msg}")
        fail_count += 1
        failed_items.append(app_num)
        errors_log.append(error_msg)
        
    except requests.exceptions.ConnectionError as conn_err:
        error_msg = f"[연결 오류] {app_num}: {type(conn_err).__name__}"
        print(f"[{idx}/{len(application_numbers)}] {app_num} - {error_msg}")
        fail_count += 1
        failed_items.append(app_num)
        errors_log.append(error_msg)
        
    except requests.exceptions.RequestException as e:
        error_msg = f"[요청 오류] {app_num}: {type(e).__name__} - {str(e)}"
        print(f"[{idx}/{len(application_numbers)}] {app_num} - {error_msg}")
        fail_count += 1
        failed_items.append(app_num)
        errors_log.append(error_msg)
        
    except Exception as e:
        error_msg = f"[예상치 못한 오류] {app_num}: {type(e).__name__} - {str(e)}"
        print(f"[{idx}/{len(application_numbers)}] {app_num} - {error_msg}")
        fail_count += 1
        failed_items.append(app_num)
        errors_log.append(error_msg)

# 에러 로그 파일로 저장
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
error_log_file = f"{log_dir}/error_log_{timestamp}.txt"

with open(error_log_file, 'w', encoding='utf-8') as f:
    f.write(f"=== 에러 로그 ===\n")
    f.write(f"생성 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"총 처리: {len(application_numbers)}개\n")
    f.write(f"성공: {success_count}개\n")
    f.write(f"실패: {fail_count}개\n")
    f.write(f"\n--- 실패한 출원번호 목록 ---\n")
    
    if failed_items:
        for item in failed_items:
            f.write(f"{item}\n")
    else:
        f.write("(없음)\n")
    
    f.write(f"\n--- 상세 에러 메시지 ---\n")
    for error in errors_log:
        f.write(f"{error}\n")

# 실패한 출원번호만 별도 파일로 저장
if failed_items:
    failed_app_file = f"{log_dir}/failed_applications_{timestamp}.txt"
    with open(failed_app_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(failed_items))
    print(f"\n📄 실패한 출원번호 목록: {failed_app_file}")

print(f"\n✅ 완료: {success_count}개 저장, {fail_count}개 실패")
print(f"📁 모든 서지상세정보 XML 파일이 '{output_dir}' 폴더에 저장되었습니다.")
print(f"📋 에러 로그: {error_log_file}")
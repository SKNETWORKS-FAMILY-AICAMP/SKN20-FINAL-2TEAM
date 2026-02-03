#!/usr/bin/env python3
"""
KIPRIS OpenAPI를 사용하여 특정 출원번호의 XML 데이터를 가져오는 스크립트
"""

import requests
import sys
import os
from pathlib import Path

# KIPRIS OpenAPI 설정
# KIPRIS Plus 디자인 정보 조회 API
KIPRIS_API_URL = "http://plus.kipris.or.kr/openapi/rest/designInfoSearchService/applicationNumberSearchInfo"

def fetch_design_xml(application_number: str, api_key: str, output_dir: str = "2000_xml"):
    """
    KIPRIS API를 통해 디자인 출원번호의 XML 데이터를 가져옵니다.
    
    Args:
        application_number: 출원번호 (예: 3020000012832)
        api_key: KIPRIS API 인증키
        output_dir: XML 파일을 저장할 디렉토리
    
    Returns:
        bool: 성공 여부
    """
    
    # API 요청 파라미터
    params = {
        'applicationNumber': application_number,
        'accessKey': api_key
    }
    
    print(f"[INFO] 출원번호 {application_number}의 데이터를 가져오는 중...")
    print(f"[INFO] API URL: {KIPRIS_API_URL}")
    
    try:
        # API 요청
        response = requests.get(KIPRIS_API_URL, params=params, timeout=30)
        
        # 응답 확인
        print(f"[INFO] 응답 상태 코드: {response.status_code}")
        
        if response.status_code != 200:
            print(f"[ERROR] API 요청 실패: HTTP {response.status_code}")
            print(f"[ERROR] 응답 내용: {response.text[:500]}")
            return False
        
        # XML 데이터 확인
        xml_data = response.text
        
        if not xml_data or len(xml_data) < 100:
            print(f"[ERROR] 유효하지 않은 XML 데이터 (길이: {len(xml_data)})")
            print(f"[ERROR] 응답 내용: {xml_data}")
            return False
        
        # 에러 메시지 확인
        if "error" in xml_data.lower() or "오류" in xml_data:
            print(f"[ERROR] API 에러 응답:")
            print(xml_data[:1000])
            return False
        
        # 출력 디렉토리 생성
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # XML 파일 저장
        xml_file = output_path / f"{application_number}.xml"
        with open(xml_file, 'w', encoding='utf-8') as f:
            f.write(xml_data)
        
        print(f"[SUCCESS] XML 파일 저장 완료: {xml_file}")
        print(f"[INFO] 파일 크기: {len(xml_data)} bytes")
        
        # XML 내용 미리보기
        print("\n[INFO] XML 데이터 미리보기 (처음 500자):")
        print("-" * 80)
        print(xml_data[:500])
        print("-" * 80)
        
        return True
        
    except requests.exceptions.Timeout:
        print(f"[ERROR] API 요청 시간 초과 (30초)")
        return False
    except requests.exceptions.RequestException as e:
        print(f"[ERROR] API 요청 중 오류 발생: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """메인 함수"""
    
    if len(sys.argv) < 2:
        print("사용법: python fetch_kipris_xml.py <출원번호> [API_KEY]")
        print("예제: python fetch_kipris_xml.py 3020000012832 your_api_key")
        print("\nAPI_KEY가 없으면 환경변수 KIPRIS_API_KEY를 사용합니다.")
        sys.exit(1)
    
    application_number = sys.argv[1]
    
    # API 키 가져오기
    if len(sys.argv) >= 3:
        api_key = sys.argv[2]
    else:
        api_key = os.environ.get('KIPRIS_API_KEY')
        if not api_key:
            print("[ERROR] API 키가 필요합니다.")
            print("방법 1: python fetch_kipris_xml.py <출원번호> <API_KEY>")
            print("방법 2: 환경변수 설정 - export KIPRIS_API_KEY='your_key'")
            sys.exit(1)
    
    # XML 가져오기
    success = fetch_design_xml(application_number, api_key)
    
    if success:
        print(f"\n✅ 성공적으로 완료되었습니다!")
        sys.exit(0)
    else:
        print(f"\n❌ 실패했습니다.")
        sys.exit(1)


if __name__ == "__main__":
    main()

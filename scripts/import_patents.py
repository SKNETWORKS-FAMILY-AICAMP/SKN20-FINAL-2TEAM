"""
특허 JSON 데이터를 MySQL로 import하는 스크립트
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path
import mysql.connector
from mysql.connector import Error

# 설정
JSON_DIR = Path(__file__).parent.parent / "json's"
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'newpassword123',
    'database': 'bini',
    'charset': 'utf8mb4'
}


def parse_date(date_str: str) -> str | None:
    """날짜 문자열을 MySQL DATE 형식으로 변환"""
    if not date_str:
        return None
    # "2005.07.04" -> "2005-07-04"
    try:
        return date_str.replace('.', '-')
    except:
        return None


def get_connection():
    """MySQL 연결"""
    return mysql.connector.connect(**DB_CONFIG)


def insert_patent(cursor, data: dict) -> int | None:
    """특허 기본 정보 삽입"""
    biblio = data.get('biblioSummaryInfoArray', {}).get('biblioSummaryInfo', {})
    abstract_info = data.get('abstractInfoArray', {}).get('abstractInfo', {})
    applicant_info = data.get('applicantInfoArray', {}).get('applicantInfo', {})

    if not biblio:
        return None

    # 출원번호에서 하이픈 제거하여 정규화
    app_num = biblio.get('applicationNumber', '').replace('-', '')
    if not app_num:
        return None

    sql = """
        INSERT INTO patents (
            application_num, register_num, open_num,
            title, title_eng, abstract,
            applicant, applicant_eng, register_status,
            application_date, register_date, open_date
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            register_num = VALUES(register_num),
            title = VALUES(title),
            register_status = VALUES(register_status)
    """

    values = (
        app_num,
        biblio.get('registerNumber', '').replace('-', '') or None,
        biblio.get('openNumber', '').replace('-', '') or None,
        biblio.get('inventionTitle', ''),
        biblio.get('inventionTitleEng', '') or None,
        abstract_info.get('astrtCont', '') or None,
        applicant_info.get('name', '') if isinstance(applicant_info, dict) else None,
        applicant_info.get('engName', '') if isinstance(applicant_info, dict) else None,
        biblio.get('registerStatus', '') or None,
        parse_date(biblio.get('applicationDate', '')),
        parse_date(biblio.get('registerDate', '')),
        parse_date(biblio.get('openDate', ''))
    )

    cursor.execute(sql, values)

    # 새로 삽입된 경우 lastrowid 반환, 업데이트된 경우 SELECT로 조회
    if cursor.lastrowid:
        return cursor.lastrowid
    else:
        cursor.execute("SELECT id FROM patents WHERE application_num = %s", (app_num,))
        result = cursor.fetchone()
        return result[0] if result else None


def insert_ipc_codes(cursor, patent_id: int, data: dict):
    """IPC 분류코드 삽입"""
    ipc_array = data.get('ipcInfoArray', {}).get('ipcInfo', [])

    if not ipc_array:
        return

    # 단일 객체인 경우 리스트로 변환
    if isinstance(ipc_array, dict):
        ipc_array = [ipc_array]

    sql = "INSERT INTO patent_ipc (patent_id, ipc_code, ipc_date) VALUES (%s, %s, %s)"

    for ipc in ipc_array:
        if isinstance(ipc, dict) and ipc.get('ipcNumber'):
            cursor.execute(sql, (
                patent_id,
                ipc.get('ipcNumber', ''),
                ipc.get('ipcDate', '') or None
            ))


def insert_claims(cursor, patent_id: int, data: dict):
    """청구항 삽입 (first_version, last_version)"""
    claims_data = data.get('claims', {})

    if not claims_data:
        return

    sql = """
        INSERT INTO claims (
            patent_id, claim_number, claim_text, claim_type,
            version_type, change_type, refers_to
        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
    """

    # first_version (출원 시 청구항)
    first_version = claims_data.get('first_version', {})
    if first_version and first_version.get('claims'):
        for claim in first_version['claims']:
            if claim.get('text'):
                cursor.execute(sql, (
                    patent_id,
                    claim.get('claim_number', 0),
                    claim.get('text', ''),
                    claim.get('claim_type', 'independent'),
                    'first',
                    claim.get('change_type', '신규'),
                    json.dumps(claim.get('refers_to', []))
                ))

    # last_version (등록 시 청구항)
    last_version = claims_data.get('last_version', {})
    if last_version and last_version.get('claims'):
        for claim in last_version['claims']:
            # 삭제된 청구항도 기록 (금반언 판단용)
            cursor.execute(sql, (
                patent_id,
                claim.get('claim_number', 0),
                claim.get('text', '') or '[삭제됨]',
                claim.get('claim_type', 'independent'),
                'last',
                claim.get('change_type', ''),
                json.dumps(claim.get('refers_to', []))
            ))


def extract_elements_from_claim(claim_text: str) -> list[dict]:
    """청구항 텍스트에서 핵심 요소 추출 (간단한 규칙 기반)"""
    elements = []

    if not claim_text or claim_text == '[삭제됨]':
        return elements

    # 성분명 패턴 (예: "헤스페리딘", "베타-시클로덱스트린")
    # 한글 성분명
    korean_pattern = r'([가-힣]+(?:[-/][가-힣]+)*(?:산|물|제|체|액|분|물질|화합물|조성물)?)'

    # 영문 성분명 (예: "tributyl acetylcitrate", "beta-cyclodextrin")
    english_pattern = r'([A-Za-z][-A-Za-z0-9]*(?:\s+[A-Za-z][-A-Za-z0-9]*)*)'

    # 숫자+단위 패턴 제외하고 의미있는 단어만 추출
    words = re.findall(r'[가-힣]{2,}|[A-Za-z]{3,}[-A-Za-z]*', claim_text)

    # 불용어 제외
    stopwords = {'있어서', '특징으로', '하는', '포함하는', '함유하는', '구성되는',
                 '있는', '따른', '에서', '으로', '에서의', '상기', '본', '발명',
                 'the', 'and', 'for', 'with', 'that', 'which', 'comprising'}

    for word in words:
        if word.lower() not in stopwords and len(word) >= 2:
            element_type = '성분' if any(c in word for c in ['산', '물', '체', '분', 'acid', 'ase']) else '기타'
            elements.append({
                'element_type': element_type,
                'element_name': word,
                'element_name_eng': word if word.isascii() else None
            })

    # 중복 제거
    seen = set()
    unique_elements = []
    for elem in elements:
        key = elem['element_name'].lower()
        if key not in seen:
            seen.add(key)
            unique_elements.append(elem)

    return unique_elements[:20]  # 최대 20개


def insert_claim_elements(cursor, claim_id: int, claim_text: str):
    """청구항에서 추출한 핵심 요소 삽입"""
    elements = extract_elements_from_claim(claim_text)

    if not elements:
        return

    sql = """
        INSERT INTO claim_elements (
            claim_id, element_type, element_name, element_name_eng, synonyms
        ) VALUES (%s, %s, %s, %s, %s)
    """

    for elem in elements:
        cursor.execute(sql, (
            claim_id,
            elem.get('element_type', '기타'),
            elem['element_name'],
            elem.get('element_name_eng'),
            json.dumps([])  # 동의어는 나중에 추가
        ))


def process_json_file(filepath: Path, cursor) -> bool:
    """단일 JSON 파일 처리"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 1. 특허 기본 정보 삽입
        patent_id = insert_patent(cursor, data)
        if not patent_id:
            return False

        # 2. IPC 코드 삽입
        insert_ipc_codes(cursor, patent_id, data)

        # 3. 청구항 삽입
        insert_claims(cursor, patent_id, data)

        # 4. 청구항 요소 추출 및 삽입 (last_version의 유효한 청구항만)
        claims_data = data.get('claims', {})
        last_version = claims_data.get('last_version', {})

        if last_version and last_version.get('claims'):
            for claim in last_version['claims']:
                if claim.get('text') and claim.get('change_type') != '삭제':
                    # claim_id 조회
                    cursor.execute("""
                        SELECT id FROM claims
                        WHERE patent_id = %s AND claim_number = %s AND version_type = 'last'
                    """, (patent_id, claim.get('claim_number', 0)))
                    result = cursor.fetchone()
                    if result:
                        insert_claim_elements(cursor, result[0], claim.get('text', ''))

        return True

    except Exception as e:
        print(f"Error processing {filepath.name}: {e}")
        return False


def main():
    """메인 함수"""
    print(f"JSON 디렉토리: {JSON_DIR}")

    # JSON 파일 목록
    json_files = list(JSON_DIR.glob("*.json"))
    total = len(json_files)
    print(f"총 {total}개 파일 발견")

    if total == 0:
        print("JSON 파일이 없습니다.")
        return

    # DB 연결
    conn = get_connection()
    cursor = conn.cursor()

    success = 0
    failed = 0

    try:
        for i, filepath in enumerate(json_files):
            if process_json_file(filepath, cursor):
                success += 1
            else:
                failed += 1

            # 100개마다 커밋 및 진행상황 출력
            if (i + 1) % 100 == 0:
                conn.commit()
                print(f"진행: {i + 1}/{total} (성공: {success}, 실패: {failed})")

        # 최종 커밋
        conn.commit()

    except Exception as e:
        print(f"Error: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

    print(f"\n완료!")
    print(f"성공: {success}")
    print(f"실패: {failed}")


if __name__ == "__main__":
    main()

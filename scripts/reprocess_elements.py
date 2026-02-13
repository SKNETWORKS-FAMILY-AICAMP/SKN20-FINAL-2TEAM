"""
claim_elements 재처리 스크립트
- kiwipiepy 형태소 분석기로 명사 추출
- 불용어 필터링 강화
- 성분 분류 개선
"""
import mysql.connector
from kiwipiepy import Kiwi
from tqdm import tqdm
import re

# DB 설정
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'newpassword123',
    'database': 'fto',
    'charset': 'utf8mb4'
}

# 불용어 목록 (확장)
STOPWORDS = {
    # 일반 불용어
    '것', '수', '등', '및', '또는', '내지', '이상', '이하', '미만', '초과',
    '약', '상기', '본', '해당', '바람직', '특히', '예를들어', '예컨대',

    # 청구항 특유 표현
    '항', '항에', '어느', '하나', '청구항', '특징', '발명', '기재', '것인',
    '것을', '이의', '갖는', '가지는', '이루어진', '선택되는', '적어도',
    '포함', '포함하는', '함유', '함유하는', '구성', '구성되는', '형성',
    '있어서', '따른', '의한', '위한', '대한', '관한', '때문', '바',

    # 조사/어미가 붙은 형태
    '경우', '방법', '단계', '과정', '수단', '용도', '목적',

    # 숫자/단위
    '제', '또', '각', '간', '중', '후', '전', '내', '외', '상', '하',

    # 영어 불용어
    'the', 'a', 'an', 'and', 'or', 'of', 'for', 'to', 'in', 'on', 'with',
    'by', 'from', 'as', 'at', 'that', 'which', 'this', 'these', 'those',
    'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
    'comprising', 'including', 'containing', 'consists', 'characterized',
}

# 성분 관련 키워드 (분류용)
INGREDIENT_PATTERNS = [
    # 화학물질 접미사
    r'.*산$', r'.*물$', r'.*제$', r'.*체$', r'.*액$', r'.*분$',
    r'.*화합물$', r'.*조성물$', r'.*추출물$', r'.*용액$', r'.*용매$',
    r'.*단백질$', r'.*펩타이드$', r'.*펩티드$', r'.*효소$',
    r'.*비타민$', r'.*아미노산$', r'.*핵산$', r'.*항체$',
    r'.*세포$', r'.*균$', r'.*바이러스$',

    # 영문 화학물질
    r'.*acid$', r'.*ase$', r'.*ose$', r'.*ol$', r'.*ine$', r'.*ide$',
    r'.*ate$', r'.*ene$', r'.*one$', r'.*yl$',
]

# 방법/기술 관련 키워드
METHOD_PATTERNS = [
    r'.*방법$', r'.*공정$', r'.*처리$', r'.*반응$', r'.*합성$',
    r'.*제조$', r'.*생산$', r'.*추출$', r'.*분리$', r'.*정제$',
    r'.*배양$', r'.*발효$', r'.*건조$', r'.*혼합$', r'.*첨가$',
]


class ElementExtractor:
    def __init__(self):
        self.kiwi = Kiwi()
        # 사용자 사전 추가 (복합어)
        self._add_user_dict()

    def _add_user_dict(self):
        """복합어 사전 추가"""
        compound_words = [
            ('나노입자', 'NNP'),
            ('나노구조체', 'NNP'),
            ('수지상세포', 'NNP'),
            ('세포막', 'NNG'),
            ('지질분자', 'NNP'),
            ('항암제', 'NNG'),
            ('면역항암', 'NNP'),
            ('화장료', 'NNG'),
            ('피부외용제', 'NNG'),
        ]
        for word, tag in compound_words:
            try:
                self.kiwi.add_user_word(word, tag)
            except:
                pass

    def extract_nouns(self, text: str) -> list[dict]:
        """텍스트에서 명사 추출"""
        if not text or text == '[삭제됨]':
            return []

        # 형태소 분석
        tokens = self.kiwi.tokenize(text)

        # 명사 추출 (NNG: 일반명사, NNP: 고유명사, NNB: 의존명사 제외)
        nouns = []
        for token in tokens:
            if token.tag in ('NNG', 'NNP'):
                word = token.form.strip()

                # 필터링
                if len(word) < 2:  # 1글자 제외
                    continue
                if len(word) > 100:  # 100자 초과 제외
                    continue
                if word.lower() in STOPWORDS:  # 불용어 제외
                    continue
                if word.isdigit():  # 숫자만 있는 것 제외
                    continue

                nouns.append(word)

        # 영문 단어 추출 (형태소 분석기가 잘 못잡는 경우)
        eng_words = re.findall(r'[A-Za-z][A-Za-z0-9-]{2,}', text)
        for word in eng_words:
            if word.lower() not in STOPWORDS and 3 <= len(word) <= 100:
                nouns.append(word)

        # 중복 제거 및 정규화
        seen = set()
        unique_nouns = []
        for noun in nouns:
            key = noun.lower()
            if key not in seen:
                seen.add(key)
                unique_nouns.append(noun)

        # 요소 생성
        elements = []
        for noun in unique_nouns[:30]:  # 최대 30개
            element_type = self._classify_element(noun)
            elements.append({
                'element_type': element_type,
                'element_name': noun,
                'element_name_eng': noun if noun.isascii() else None
            })

        return elements

    def _classify_element(self, word: str) -> str:
        """요소 분류"""
        word_lower = word.lower()

        # 성분 패턴 매칭
        for pattern in INGREDIENT_PATTERNS:
            if re.match(pattern, word_lower):
                return '성분'

        # 방법 패턴 매칭
        for pattern in METHOD_PATTERNS:
            if re.match(pattern, word_lower):
                return '방법'

        return '기타'


def backup_table(cursor):
    """기존 테이블 백업"""
    print("기존 claim_elements 백업 중...")
    cursor.execute("DROP TABLE IF EXISTS claim_elements_backup")
    cursor.execute("CREATE TABLE claim_elements_backup AS SELECT * FROM claim_elements")
    print("백업 완료: claim_elements_backup")


def truncate_table(cursor):
    """기존 데이터 삭제"""
    print("기존 claim_elements 데이터 삭제 중...")
    cursor.execute("TRUNCATE TABLE claim_elements")
    print("삭제 완료")


def get_claims(cursor):
    """유효한 청구항 조회 (last_version, 삭제 제외)"""
    cursor.execute("""
        SELECT id, claim_text
        FROM claims
        WHERE version_type = 'last'
          AND (change_type IS NULL OR change_type != '삭제')
          AND claim_text IS NOT NULL
          AND claim_text != '[삭제됨]'
    """)
    return cursor.fetchall()


def insert_elements(cursor, claim_id: int, elements: list[dict]):
    """요소 삽입"""
    if not elements:
        return

    sql = """
        INSERT INTO claim_elements
        (claim_id, element_type, element_name, element_name_eng, synonyms)
        VALUES (%s, %s, %s, %s, '[]')
    """

    for elem in elements:
        cursor.execute(sql, (
            claim_id,
            elem['element_type'],
            elem['element_name'],
            elem.get('element_name_eng')
        ))


def main():
    print("=" * 60)
    print("claim_elements 재처리 시작")
    print("=" * 60)

    # DB 연결
    conn = mysql.connector.connect(**DB_CONFIG)
    cursor = conn.cursor()

    try:
        # 1. 백업
        backup_table(cursor)
        conn.commit()

        # 2. 기존 데이터 삭제
        truncate_table(cursor)
        conn.commit()

        # 3. 청구항 조회
        print("\n청구항 조회 중...")
        claims = get_claims(cursor)
        print(f"처리할 청구항: {len(claims)}건")

        # 4. 요소 추출기 초기화
        extractor = ElementExtractor()

        # 5. 처리
        total_elements = 0
        batch_size = 500

        for i, (claim_id, claim_text) in enumerate(tqdm(claims, desc="처리 중")):
            elements = extractor.extract_nouns(claim_text)
            insert_elements(cursor, claim_id, elements)
            total_elements += len(elements)

            # 배치 커밋
            if (i + 1) % batch_size == 0:
                conn.commit()

        # 최종 커밋
        conn.commit()

        # 6. 결과 확인
        cursor.execute("SELECT COUNT(*) FROM claim_elements")
        new_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM claim_elements_backup")
        old_count = cursor.fetchone()[0]

        print("\n" + "=" * 60)
        print("처리 완료!")
        print("=" * 60)
        print(f"기존 요소 수: {old_count:,}")
        print(f"신규 요소 수: {new_count:,}")
        print(f"변화: {new_count - old_count:+,}")

        # 요소 타입별 통계
        cursor.execute("""
            SELECT element_type, COUNT(*) as cnt
            FROM claim_elements
            GROUP BY element_type
            ORDER BY cnt DESC
        """)
        print("\n요소 타입별 분포:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]:,}")

        # 상위 요소명
        cursor.execute("""
            SELECT element_name, COUNT(*) as cnt
            FROM claim_elements
            GROUP BY element_name
            ORDER BY cnt DESC
            LIMIT 20
        """)
        print("\n상위 20개 요소:")
        for row in cursor.fetchall():
            print(f"  {row[0]}: {row[1]:,}")

    except Exception as e:
        print(f"\n오류 발생: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()

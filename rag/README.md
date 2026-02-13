# RAG 시스템 종합 설명서

> 특허 침해 여부 사전 검증을 위한 하이브리드 검색 시스템

---

## 전체 파이프라인

```
사용자 입력 "헤스페리딘과 비타민C가 포함된 주름 개선 화장품"
    │
    ▼
[1] multi_query.py ── 성분 추출 + 쿼리 조합 생성 (8개)
    │
    ▼
[2] retriever.py ─── Dense(KURE-v1) + Sparse(BM25) 각각 검색
    │
    ▼
[3] retriever.py ─── RRF 점수 합산 → Patent Collapse (특허당 1개)
    │
    ▼
[4] filter.py ────── 등록 필터 + 금반언 표시 + 데이터 보강
    │
    ▼
최종 결과: [{patent_id, score, matched_claim_num, claims, estoppel, ...}, ...]
```

---

## 디렉토리 & 파일 설명

```
v1/rag/
├── config.py
├── pipeline.py
├── backend_adapter.py
├── requirements.txt
├── build/
│   ├── tokenizer.py
│   ├── chunker.py
│   └── indexer.py
├── search/
│   ├── retriever.py
│   ├── multi_query.py
│   └── filter.py
├── eval/
│   ├── build_index.py
│   ├── evaluate.py
│   ├── interactive_test.py
│   ├── data/
│   └── reports/
└── index/                  ← 빌드 산출물 (gitignored)
```

### 루트 파일

| 파일 | 설명 |
|------|------|
| `config.py` | 모든 설정값 한곳에 모아둔 파일. 경로, 모델, 검색 파라미터 등. 값 바꾸면 전체 반영 |
| `pipeline.py` | **검색 진입점**. `search()` 함수 하나로 위 파이프라인 전체 실행. evaluate, backend_adapter 등이 이걸 호출 |
| `backend_adapter.py` | 백엔드(FastAPI)에서 RAG를 쓰기 위한 래퍼. Standalone(JSON) / MySQL 연동 둘 다 지원 |
| `requirements.txt` | Python 의존성 목록 |

### build/ — 인덱스 빌드 (1회 실행)

| 파일 | 설명 |
|------|------|
| `tokenizer.py` | kiwipiepy 형태소 분석기 싱글톤. BM25 토크나이징 전용. **성분 추출에 쓰면 안 됨** (도메인 용어 파괴: "곰의말채"→"곰","말","채") |
| `chunker.py` | 특허 JSON → 청크 변환 + claims_db.json 생성. 청킹 전략 상세 내용은 아래 참조 |
| `indexer.py` | 청크 → Dense 인덱스(ChromaDB) + Sparse 인덱스(BM25 pickle) 생성 |

### search/ — 검색 런타임

| 파일 | 설명 |
|------|------|
| `retriever.py` | Dense/Sparse 검색 실행 + RRF 점수 합산 + Patent Collapse |
| `multi_query.py` | 사용자 쿼리에서 성분을 추출하고 검색 조합을 생성. regex 기반(기본) / LLM fallback |
| `filter.py` | 검색 결과 후처리. 미등록 특허 제거, 금반언 청구항 표시, 청구항 텍스트 보강 |

### eval/ — 평가/테스트 도구

| 파일 | 설명 |
|------|------|
| `build_index.py` | 원커맨드 인덱스 빌더. `python -m v1.rag.eval.build_index --data-dir temp_json_samples` |
| `evaluate.py` | Hit Rate@K, MRR 자동 측정. 결과를 reports/에 텍스트 보고서로 저장 |
| `interactive_test.py` | 대화형 검색 REPL. 쿼리 입력 → 성분 추출 + 검색 결과 확인 |
| `data/` | 테스트 데이터셋 (test_dataset_sample14.xlsx 등) |
| `reports/` | 평가 보고서 자동 저장 (eval_YYYYMMDD_HHMMSS.txt) |

### index/ — 빌드 산출물

| 파일 | 설명 |
|------|------|
| `chroma_db/` | Dense 임베딩 벡터 DB (KURE-v1, 1024차원) |
| `bm25.pkl` | Sparse 인덱스 (BM25Okapi + chunk_id 매핑) |
| `chunks.json` | 전체 청크 데이터 (dense_text, sparse_text, full_text, metadata) |
| `claims_db.json` | RDB 대체용 JSON. 특허별 청구항·금반언 정보. 백엔드 MySQL 연동 시 사용 안 함 |

---

## 청킹 전략: Dual-View Claim Chunk

### 분할 단위

**독립항 그룹** 단위로 분할. 1개 독립항 + 그에 딸린 종속항들 = 1 청크.

```
특허 1개 (독립항 3개, 종속항 7개)
  → 청크 1: 독립항1 + 종속항(2,3,4)
  → 청크 2: 독립항5 + 종속항(6,7)
  → 청크 3: 독립항8 + 종속항(9,10)
```

- 3,271 특허 × 평균 2.5 독립항 = ~8,000 청크 예상
- 청크당 ~800~1800자 → KURE-v1 토큰 한계(8192) 내 안전

### 왜 이렇게 하는가

| 이전 시도 | 결과 | 실패 원인 |
|-----------|------|-----------|
| 독립항 1개 = 1청크 (제목+청구항만) | 65% | 컨텍스트 부족 |
| 특허 1개 = 1청크 | 토큰 초과 8.6% | 대형 특허가 8192토큰 넘음 |
| 슬라이딩 윈도우 (글자수 기준) | ~80% | 청구항 중간 절단 |

**교훈**: 독립항 단위 분할 + 풍부한 컨텍스트 + Dense/Sparse 별도 전처리

### Dual-View: Dense와 Sparse에 다른 텍스트를 먹인다

```
                 같은 청크
                    │
         ┌──────────┴──────────┐
         ▼                     ▼
    dense_text              sparse_text
  (자연어, 의미 풍부)      (키워드 농축, 노이즈 제거)
         │                     │
         ▼                     ▼
    ChromaDB (KURE-v1)      BM25 (kiwipiepy)
    의미적 매칭              키워드 정확 매칭
  "비타민C" ↔ "아스코르브산"  "헤스페리딘" = "헤스페리딘"
```

**dense_text** — 자연어 흐름 유지, 임베딩 품질 극대화:
```
[발명] 헤스페리딘 유도체를 함유하는 한방 액제
[분야] A61K 31/7048, A61K 47/50
[요약] 본 발명은 헤스페리딘과 베타-시클로덱스트린의 포접화합물을...
[독립항 1] 헤스페리딘과 베타-시클로덱스트린의 포접화합물을...
[종속항 2] 제1항에 있어서, ...
```

**sparse_text** — 법률 상용구/숫자 제거 → kiwipiepy NNG/NNP/SL만 추출:
```
헤스페리딘 유도체 베타 시클로덱스트린 포접 화합물 한방 액제 화장료 조성물
```

---

## 하이브리드 검색 & RRF

### Dense 검색
- 모델: **KURE-v1** (nlpai-lab/KURE-v1, 1024차원, max 8192토큰)
- 저장소: **ChromaDB** (cosine 유사도)
- 역할: 의미적 매칭 — 동의어, 유사어 브릿지

### Sparse 검색
- 알고리즘: **BM25Okapi** (rank_bm25)
- 토크나이저: **kiwipiepy** (NNG, NNP, SL 추출)
- 역할: 키워드 정확 매칭 — 성분명 직접 매칭

### RRF (Reciprocal Rank Fusion)

```
score(d) = 0.4 / (60 + rank_dense) + 0.6 / (60 + rank_sparse)
```

| 파라미터 | 값 | 의미 |
|----------|-----|------|
| **RRF_K** | 60 | 순위 기반 합산 상수 (표준값) |
| **RRF_WEIGHTS** | (0.4, 0.6) | Dense 40%, Sparse 60% — BM25에 좀 더 가중 |
| DENSE_TOP_K | 50 | Dense 검색 시 쿼리당 50개 후보 |
| BM25_TOP_K | 50 | Sparse 검색 시 쿼리당 50개 후보 |
| FINAL_TOP_K | 10 | 최종 반환 특허 수 |

### Patent Collapse

같은 특허의 여러 독립항 청크 중 **최고 RRF 점수 1개만** 남김.
예: 특허X 독립항1(0.05) + 독립항5(0.03) → 독립항1(0.05)만 대표로 반환.

---

## 멀티쿼리

사용자가 "a, b, c를 포함하는 주름 화장품" 검색 시, 성분 조합을 확장:

| 쿼리 | 목적 |
|------|------|
| 원본 전체 | 전체 맥락 매칭 |
| a 주름 화장품 | 성분a 단독 + 분야 |
| b 주름 화장품 | 성분b 단독 + 분야 |
| c 주름 화장품 | 성분c 단독 + 분야 |
| a b | 2성분 조합 |
| a c | 2성분 조합 |
| b c | 2성분 조합 |
| a b c | 전체 성분 |

성분 추출: **regex 구조 기반** (기본). "~를 포함/사용/함유" 앞 영역에서 쉼표·접속사로 분리.
kiwipiepy로 성분 추출 절대 금지 (도메인 용어 파괴됨).

---

## 금반언 (Estoppel)

특허 출원→등록 과정에서 **삭제된 청구항**은 침해 판단 근거로 사용 불가 (법적 원칙).
RAG가 직접 제거하지 않고, `estoppel_claim_numbers` 필드로 표시하여 sLLM이 판단 시 참고.

---

## 실행 명령어

```bash
# 인덱스 빌드 (최초 1회)
python -m v1.rag.eval.build_index --data-dir temp_json_samples

# 강제 재빌드 (전처리 로직 변경 시)
python -m v1.rag.eval.build_index --data-dir temp_json_samples --force

# 대화형 검색 테스트
python -m v1.rag.eval.interactive_test

# 테스트셋 평가
python -m v1.rag.eval.interactive_test --eval

# 코드에서 사용
from v1.rag.pipeline import search
results = search("헤스페리딘이 포함된 한방 액제", verbose=True)
```

---

## 현재 성능 (샘플 14개 / 20쿼리)

| 지표 | 결과 |
|------|------|
| Hit Rate@1 | **95.0%** |
| Hit Rate@3 | **100.0%** |
| MRR | **0.9750** |

> 샘플 기반 테스트라 난이도 낮음. 풀셋(3,271건)에서는 하락 예상.

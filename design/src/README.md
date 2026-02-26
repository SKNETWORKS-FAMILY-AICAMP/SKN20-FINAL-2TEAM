# 디자인 유사성 분석 챗봇

CLIP 임베딩 기반 **Hybrid Retrieval**과 **GPT-4o VLM**을 활용한 디자인 특허 유사도 분석 시스템

---

## 전체 구조

```
[입력]
  │
  ├─ 이미지 ──▶ [VLM 분석] ──▶ [유사 디자인 검색] ──▶ [선택 대기] ──▶ [상세 비교] ──▶ [FTO 리포트]
  │
  └─ 텍스트 ──▶ [LLM + Tools]
```

---

## 이미지 입력 플로우

### 1단계 · VLM 분석
GPT-4o가 입력 이미지의 형상·구조·외관을 텍스트로 분석

---

### 2단계 · 유사 디자인 검색 (Hybrid Retrieval)

**전처리 — 쿼리 이미지 → 스케치 변환**

DB에 저장된 임베딩은 스케치 변환 이미지 기준이므로, 쿼리 이미지도 동일한 전처리 적용

```
원본 이미지
  └─▶ GaussianBlur (5×5, σ=1.0)
        └─▶ Canny Edge Detection (threshold: 30 / 120)
              └─▶ Dilate (2×2 kernel, 1회)
                    └─▶ 흰 배경 + 검은 윤곽선
```

**검색 — Dense + BM25 2단계**

| 단계 | 방법 | 범위 | 결과 |
|:---:|---|---|---|
| ① Dense | CLIP ViT-B/32 임베딩 → ChromaDB 코사인 유사도 | 전체 DB | 상위 50개 후보 |
| ② BM25 | Dense 1위의 `articleName` 키워드 → 텍스트 재점수 | 50개 내 재랭킹 | - |
| ③ 합산 | min-max 정규화 후 가중 합산 | Dense **0.7** + BM25 **0.3** | - |
| ④ 중복 제거 | 동일 출원번호 중 `hybrid_score` 최고 도면 유지 | - | - |
| ⑤ 반환 | `hybrid_score` 내림차순 정렬 | - | **최종 10개** |

---

### 3단계 · 사용자 선택 _(interrupt)_

- 검색 결과 10개를 `hybrid_score` 기준으로 출력
- 사용자가 상세 비교할 도면 번호 선택 → 그래프 재개

---

### 4단계 · 상세 비교

- 선택한 도면 이미지를 GPT-4o가 입력 이미지와 나란히 비교
- 유사점 / 차이점 분석 결과 생성

---

### 5단계 · FTO 리포트 생성

- VLM 분석 결과 + 상세 비교 결과 → 최종 FTO 리포트 출력

---

## 텍스트 입력 플로우

LLM이 질문을 보고 필요한 Tool을 자동 선택하여 답변

| Tool | 동작 |
|---|---|
| `web_search` | Tavily를 통한 웹 검색 (특허 뉴스, 법률 정보 등) |
| `search_design_db` | 자연어 → CLIP 임베딩 → ChromaDB 디자인 검색 |

---

## 주요 파일

| 파일 | 역할 |
|---|---|
| `src/design_chatbot.py` | 챗봇 메인 — LangGraph 그래프 및 노드 정의 |
| `src/utils.py` | 임베딩, 스케치 변환, Hybrid Retrieval 유틸 함수 |
| `src/prompts.py` | VLM 분석 / 비교 / 리포트 프롬프트 |
| `build/vectordb.py` | ChromaDB 벡터 DB 구축 |
| `build/embeddings.py` | 이미지 → CLIP 임베딩 생성 |

---


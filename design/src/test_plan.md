# Qwen2.5-VL-7B-Instruct 테스트 계획

> GPT-4o → sLLM 교체 후 품질 검증
> 기준 결과(GPT-4o)와 비교하여 갭 파악

---

## 테스트 환경

| 항목 | 내용 |
|------|------|
| 모델 | `/workspace/Qwen2.5-VL-7B-Instruct` |
| 서빙 | vLLM on RunPod (`VLLM_API_BASE` 환경변수) |
| 실행 | `langchain` conda 환경 |
| 실행 위치 | `design/src/` |

---

## 테스트 케이스

### TC-1. 이미지 입력 → 유사 디자인 검색 + 상세 비교 + FTO 리포트

**입력**
```
image_path = "design/data/images/3019810003379-api_xml-1_001.JPG"
```

**확인 항목**
1. `analyze_image_node`: 이미지 형상 설명이 구체적인가? (전체 형태, 캡 구조, 몸체 등)
2. `image_search_node`: 유사 디자인 N개 정상 반환되는가?
3. `detailed_compare_node`: 유사점/차이점이 구체적으로 나열되는가?
4. `generate_report_node`: 아래 6개 섹션이 모두 포함되는가?
   - [ ] 1. 입력 디자인 요약
   - [ ] 2. 비교 디자인 정보 (출원번호, 등록상태)
   - [ ] 3. 유사한 점
   - [ ] 4. 차이점
   - [ ] 5. FTO 판단
   - [ ] 6. 주의사항/종합 의견

**GPT-4o 기준 결과 (노트북)**
- 분석 211자, 유사 8개 발견
- 리포트 963자, 6개 섹션 완성

---

### TC-2. 일반 질문 (Tool 없이 직접 답변)

**입력**
```
text_query = "디자인 특허 출원 절차가 뭐야?"
```

**확인 항목**
- Tool 호출 없이 직접 답변하는가?
- 출원 절차 단계가 순서대로 나열되는가? (준비 → 조사 → 작성 → 제출 → 심사 → 등록)
- 한국어 자연스러운가?

**GPT-4o 기준 결과**: 8단계 절차 목록, 마크다운 형식

---

### TC-3. DB 검색 Tool 호출

**입력**
```
text_query = "펌프형 용기 디자인 찾아줘"
```

**확인 항목**
- `search_design_db` tool이 호출되는가?
- 한국어 → 영어 번역 후 검색하는가? (`펌프형 용기` → `Pump container`)
- 검색 결과(출원번호, 등록상태)가 응답에 포함되는가?

**GPT-4o 기준 결과**: tool 호출 성공, 5개 디자인 목록 반환

---

### TC-4. 웹 검색 Tool 호출

**입력**
```
text_query = "2024년 디자인 특허 출원 통계 알려줘"
```

**확인 항목**
- `web_search` tool이 호출되는가?
- 실제 통계 수치가 응답에 포함되는가?
- 출처가 언급되는가?

**GPT-4o 기준 결과**: tool 호출 성공, 출원 통계 수치 포함

---

## 평가 기준 (간단 채점)

| 등급 | 기준 |
|------|------|
| ✅ 통과 | GPT-4o 결과와 동등하거나 핵심 내용 포함 |
| ⚠️ 미흡 | 내용은 있으나 GPT-4o 대비 누락/부정확 |
| ❌ 실패 | 오류 발생 또는 응답 불가 |

---

## 실행 방법

```python
# langchain 환경에서 실행
# design/src/ 위치에서

from design_chatbot import run_chatbot, graph

# TC-1: 이미지
result = run_chatbot(image_path="../data/images/3019810003379-api_xml-1_001.JPG")

# TC-2: 일반 질문
result = run_chatbot(text_query="디자인 특허 출원 절차가 뭐야?")

# TC-3: DB 검색
result = run_chatbot(text_query="펌프형 용기 디자인 찾아줘")

# TC-4: 웹 검색
result = run_chatbot(text_query="2024년 디자인 특허 출원 통계 알려줘")
```

---

## 결과 기록

| TC | 항목 | GPT-4o | Qwen2.5-VL | 판정 |
|----|------|--------|------------|------|
| TC-1 | 이미지 분석 품질 | 211자, 구체적 | | |
| TC-1 | 리포트 섹션 완성도 | 6/6 섹션 | | |
| TC-2 | 일반 질문 답변 | 8단계 절차 | | |
| TC-3 | DB tool 호출 | 성공 | | |
| TC-4 | 웹 tool 호출 | 성공 | | |

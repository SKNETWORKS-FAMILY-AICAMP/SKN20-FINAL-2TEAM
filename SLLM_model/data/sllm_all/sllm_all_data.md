# sLLM 학습 데이터

## 데이터 출처

- 원본: `fto_dataset_gemini-2.0-flash_20260216_all.xlsx` (36,577행, 9,155개 특허)
- 19개 평가 규칙 전체 PASS된 데이터만 필터링 → 26,073행, 9,003개 특허
- 특허 단위 8:2 분할 (같은 특허의 모든 라벨은 동일 세트에 포함)

## 파일

| 파일 | 행 수 | 특허 수 |
|------|-------|---------|
| `data/sllm_train.xlsx` | 20,834 | 7,202 |
| `data/sllm_test.xlsx` | 5,239 | 1,801 |
| **합계** | **26,073** | **9,003** |

## 라벨 분포

### Train (20,834행, 7,202개 특허)

| 라벨 | 건수 | 비율 |
|------|------|------|
| 침해 | 6,407 | 30.8% |
| 비침해 | 5,664 | 27.2% |
| 애매 | 4,383 | 21.0% |
| 침해_전문가 | 4,380 | 21.0% |

### Test (5,239행, 1,801개 특허)

| 라벨 | 건수 | 비율 |
|------|------|------|
| 침해 | 1,598 | 30.5% |
| 비침해 | 1,420 | 27.1% |
| 애매 | 1,120 | 21.4% |
| 침해_전문가 | 1,101 | 21.0% |

## 컬럼

| 컬럼 | 설명 |
|------|------|
| apply_num | 출원번호 |
| regit_num | 등록번호 |
| pub_num | 공개번호 |
| components | 추출된 구성요소 |
| user_query | 사용자 질문 |
| claim_reg | 등록청구항 |
| claim_pub | 공개청구항 |
| output_form | FTO 판단 출력 |
| label | 라벨 (침해/비침해/애매/침해_전문가) |

## 평가 규칙 (19개)

| # | 규칙 | 카테고리 |
|---|------|----------|
| 1 | conclusion_phrase | 출력 형식 |
| 2 | forbidden_words | 출력 형식 |
| 3 | query_patent_terms | 질문 품질 |
| 4 | uncertain_rule | 법리 검증 |
| 5 | correspondence_values | 출력 형식 |
| 6 | table_row_count | 출력 형식 |
| 7 | table_header | 출력 형식 |
| 8 | infringement_no_mismatch | 법리 검증 |
| 9 | non_infringement_all_match | 법리 검증 |
| 10 | expert_needs_equiv_or_inherent | 법리 검증 |
| 11 | infringement_has_equiv_or_inherent | 법리 검증 |
| 12 | expert_has_plain_mismatch | 법리 검증 |
| 13 | non_infringement_only_equiv_or_inherent | 법리 검증 |
| 14 | infringement_judgment_opening | 판단 품질 |
| 15 | query_no_comparison | 질문 품질 |
| 16 | component_claim_reference | 구성요소 품질 |
| 17 | product_by_process_unexpanded | 구성요소 품질 |
| 18 | result_judgment_dup | 출력 형식 |
| 19 | query_no_formulation_terms | 질문 품질 |

## 생성 모델

- Gemini 2.0 Flash (`gemini-2.0-flash`)

# eval 모듈 사용법

## 1. interactive_test - 대화형 검색 테스트

RAG 검색 결과를 직접 확인하는 REPL입니다.

```bash
# v1/ 폴더가 있는 디렉토리에서 실행
cd <v1이 있는 디렉토리>
python -m v1.rag.eval.interactive_test           # 기본
python -m v1.rag.eval.interactive_test --verbose  # 상세 로그
python -m v1.rag.eval.interactive_test --eval     # 테스트셋 자동 평가만
```

### REPL 명령어

| 명령어 | 설명 |
|--------|------|
| (쿼리 입력) | 검색 실행 |
| `/report` | 현재까지 결과를 보고서로 저장 |
| `/claim N` | 마지막 결과의 N번째 특허 청구항 전문 보기 |
| `/abstract N` | 마지막 결과의 N번째 특허 초록 전문 보기 |
| `eval` | 테스트셋 평가 실행 |
| `q` / `quit` / `Ctrl+C` | 종료 (보고서 자동 저장) |

### 보고서

종료 시 `eval/reports/manual/`에 JSON + MD 보고서가 자동 저장됩니다.

---

## 2. chatbot - GPT 침해 분석 챗봇

RAG 검색 + GPT-4o-mini로 특허 침해 분석까지 수행합니다.
`.env`에 `OPENAI_API_KEY`가 필요합니다.

```bash
# v1/ 폴더가 있는 디렉토리에서 실행
cd <v1이 있는 디렉토리>
python -m v1.rag.eval.chatbot.run
```

### REPL 명령어

| 명령어 | 설명 |
|--------|------|
| (제품 설명 입력) | 첫 입력 시 자동으로 검색 + 침해 분석 |
| (후속 질문 입력) | 대화 이력 유지하며 추가 질의 |
| `/search <쿼리>` | 새로운 제품으로 재검색 |
| `/clear` | 대화 초기화 |
| `q` / `quit` / `Ctrl+C` | 종료 |

### 차이점

| | interactive_test | chatbot |
|--|-----------------|---------|
| 기능 | 검색만 | 검색 + GPT 침해 분석 |
| API 키 | 불필요 | OPENAI_API_KEY 필요 |
| 보고서 | 자동 저장 | 없음 |
| 용도 | 리트리버 성능 확인 | 전체 파이프라인 검증 |

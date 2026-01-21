# 셀럽 코디 추천 시스템 (Celebrity Fashion RAG)

## 프로젝트 개요

사용자가 자신의 옷 사진을 업로드하면, **LangGraph Agent** + **Korean CLIP** 기반 RAG 시스템을 통해
저장된 셀럽 코디 중 유사한 스타일을 찾아 추천해주는 시스템입니다.

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────────────────┐
│              LangGraph Agent + Korean CLIP 패션 추천 시스템               │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                    StateGraph (워크플로우)                        │   │
│  │                                                                  │   │
│  │   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐   │   │
│  │   │   Node 1     │     │   Node 2     │     │   Node 3     │   │   │
│  │   │ embed_image  │ --> │ search_sim   │ --> │ generate_rec │   │   │
│  │   │ (CLIP)       │     │ (Chroma)     │     │ (GPT)        │   │   │
│  │   └──────────────┘     └──────────────┘     └──────────────┘   │   │
│  │                                                                  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                         │
│  [Korean CLIP]                                                          │
│  이미지 → 512차원 벡터 (직접 임베딩, 텍스트 변환 없음)                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

## 기술 스택

| 구분 | 기술 |
|------|------|
| **Agent 프레임워크** | LangGraph |
| **이미지 임베딩** | Korean CLIP (OpenCLIP ViT-B-32) |
| **벡터 저장소** | LangChain Chroma |
| **추천 메시지 생성** | GPT-4o-mini |
| **웹 인터페이스** | Gradio |
| **언어** | Python 3.11 |
| **환경** | conda fs |

## Korean CLIP vs GPT-4o Vision

| 항목 | Korean CLIP (현재) | GPT-4o Vision |
|------|-------------------|---------------|
| **처리 방식** | 이미지 → 벡터 (1단계) | 이미지 → 텍스트 → 벡터 (2단계) |
| **정확도** | 시각적 유사도 직접 비교 | 텍스트 변환 시 정보 손실 |
| **비용** | 무료 (로컬 실행) | 유료 (~$0.01/이미지) |
| **속도** | 빠름 | API 대기 시간 |

## LangGraph Agent 노드 설명

### Node 1: `embed_image`
- **역할**: 이미지를 벡터로 직접 임베딩
- **입력**: 사용자 이미지 경로
- **출력**: 512차원 벡터
- **사용 모델**: OpenCLIP ViT-B-32

### Node 2: `search_similar`
- **역할**: 유사한 셀럽 코디 검색
- **입력**: 이미지 임베딩 벡터
- **출력**: 상위 3개 유사 코디
- **사용 DB**: LangChain Chroma

### Node 3: `generate_recommendation`
- **역할**: 맞춤 추천 메시지 생성
- **입력**: 검색된 코디 정보
- **출력**: AI 스타일리스트 추천 메시지
- **사용 모델**: GPT-4o-mini

## 파일 구조

```
C:\00AI\project\project_final\rag\
├── CLAUDE.md               # 프로젝트 기획서 (현재 파일)
├── requirements.txt        # 패키지 의존성
├── config.py              # 설정 파일
├── embed_celeb_fashion.py # 셀럽 코디 임베딩 스크립트 (최초 1회)
├── agent.py               # LangGraph Agent 핵심 로직
├── app.py                # Gradio 웹 인터페이스
├── RAG/                  # 셀럽 코디 이미지 폴더
│   ├── JWJ_1.jpg
│   ├── JWJ_2.jpg
│   └── ...
└── chroma_db/            # 벡터 저장소 (자동 생성)
```

## 사용 방법

### 1. 환경 설정
```bash
conda activate fs
pip install -r requirements.txt
```

### 2. 환경 변수 설정 (추천 메시지 생성용, 선택사항)
```bash
# Windows
set OPENAI_API_KEY=your_api_key_here

# 또는 .env 파일 생성
echo OPENAI_API_KEY=your_api_key_here > .env
```
> **Note**: OpenAI API 키가 없어도 유사도 검색은 동작합니다. 추천 메시지만 기본 형태로 표시됩니다.

### 3. 셀럽 코디 임베딩 (최초 1회)
```bash
python embed_celeb_fashion.py
```
- RAG 폴더의 모든 이미지를 Korean CLIP으로 임베딩
- 처음 실행 시 CLIP 모델 다운로드 (~350MB)
- GPU 있으면 더 빠름 (CPU도 가능)

### 4. 웹 앱 실행
```bash
python app.py
```
http://localhost:7860 에서 접속

### 5. CLI 테스트 (선택)
```bash
python agent.py <이미지_경로>
```

## Agent 상태 (State) 구조

```python
class FashionAgentState(TypedDict):
    # 입력
    user_image_path: str

    # 중간 결과
    user_embedding: list[float]    # 512차원 CLIP 벡터

    # 검색 결과
    recommendations: list[dict]    # 유사 코디 목록

    # 최종 출력
    recommendation_message: str    # AI 추천 메시지
    error: str | None             # 에러 메시지
```

## API 비용 참고

| 항목 | 비용 |
|------|------|
| Korean CLIP 임베딩 | 무료 (로컬) |
| GPT-4o-mini 추천 메시지 | ~$0.0001/요청 |

## 에러 처리

LangGraph의 조건부 엣지를 활용하여 각 노드에서 에러 발생 시
즉시 종료하고 에러 메시지를 반환합니다.

## 향후 개선 사항

1. **한국어 특화 CLIP**: koclip 등 한국어 전용 모델로 교체
2. **스트리밍 출력**: 각 노드 실행 상태를 실시간으로 표시
3. **다중 의류 분석**: 한 이미지에서 여러 의류 아이템 개별 분석
4. **스타일 조합 추천**: 상의/하의 조합 추천
5. **계절/TPO 필터링**: 상황에 맞는 코디 필터링

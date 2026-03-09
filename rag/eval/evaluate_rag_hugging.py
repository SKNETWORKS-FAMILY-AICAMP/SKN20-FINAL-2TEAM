"""
RAGAS 기반 RAG 시스템 평가

rag_system.py의 RAG 시스템을 RAGAS 메트릭으로 평가

평가 지표:
1. Context Recall - 검색된 컨텍스트가 ground truth를 얼마나 포함하는지
2. Context Precision - 검색된 컨텍스트 중 관련 있는 것의 비율
3. Faithfulness - 답변이 컨텍스트에 기반하는지 (할루시네이션 방지)
4. Answer Relevancy - 답변이 질문과 관련이 있는지
5. Answer Correctness - 답변이 ground truth와 얼마나 일치하는지
"""

import os
import re
import sys
import csv
import warnings
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
from dotenv import load_dotenv

# 경고 무시
warnings.filterwarnings("ignore")

# RAGAS 관련 임포트
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
    answer_correctness,
)
from ragas.embeddings import LangchainEmbeddingsWrapper
from datasets import Dataset

# LangChain 임포트
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.documents import Document

# RAG 시스템 모듈 임포트 (변수가 아닌 모듈 자체를 임포트)
from . import evaluate_rag_system

# 환경 변수 로드
load_dotenv()

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent


# ===== 평가용 데이터셋 정의 =====
# Ground Truth: 실제 RAG 답변 형식과 동일하게 (내용 요약 + 메타데이터)
EVALUATION_DATASET = [
    {
        "question": "ToolOrchestra: Elevating Intelligence via Efficient Model and Tool Orchestration",
        "ground_truth": """1) ToolOrchestra는 소형 오케스트레이터를 통해 다양한 지능형 도구를 효율적으로 조정하여 복잡한 작업을 해결하는 프레임워크입니다.

2) 주요 통찰:
- 강화 학습을 사용하여 소형 오케스트레이터가 다른 모델과 도구를 관리하도록 훈련합니다.
- Orchestrator 모델은 GPT-5보다 높은 정확도와 낮은 비용으로 복잡한 문제를 해결합니다.
- 다양한 도구를 조합하여 효율적인 도구 보강 추론 시스템을 구축할 수 있습니다.

3) ToolOrchestra는 LLM 기반 에이전트가 효율적으로 도구와 모델을 오케스트레이션하는 방법을 제시합니다.

[출처]
- 논문: ToolOrchestra: Elevating Intelligence via Efficient Model and Tool Orchestration
  HuggingFace URL: https://huggingface.co/papers/2511.21689
  GitHub: https://github.com/NVlabs/ToolOrchestra/
  저자: Hongjin Su, Shizhe Diao, Ximing Lu
  Upvote: 99""",
        "expected_title": "ToolOrchestra",
        "search_type": "paper",
    },
    {
        "question": "RFT를 LVLMs (large video language models) 으로 확장하는 방법은 무엇이 있나요?",
        "ground_truth": """1) VideoP2R은 RFT를 Large Video Language Models로 확장하는 프레임워크입니다.

2) 주요 통찰:
- 비디오 이해를 위해 인식과 추론을 별도의 과정으로 모델링합니다.
- SFT 단계에서 고품질의 체인 오브 생각(CoT) 데이터셋을 생성합니다.
- RL 단계에서 인식과 추론에 대해 별도의 보상을 제공하는 PA-GRPO 알고리즘을 도입합니다.

3) VideoP2R은 비디오 추론 및 이해의 여러 벤치마크에서 최첨단 성능을 달성합니다.

[출처]
- 논문: VIDEOP2R: Video Understanding from Perception to Reasoning
  HuggingFace URL: https://huggingface.co/papers/2511.11113
  저자: Yifan Jiang, Yueying Wang, Rui Zhao, Toufiq Parag
  Upvote: 111""",
        "expected_title": "VIDEOP2R",
        "search_type": "paper",
    },
    {
        "question": "LLM에서 긴 문맥의 추론을 향상시키는 GSW (Generative Semantic Workspace)에 대한 논문이 있다면 소개시켜주세요",
        "ground_truth": """1) GSW(Generative Semantic Workspace)는 LLM의 긴 문맥 추론 능력을 향상시키는 신경 영감을 받은 메모리 프레임워크입니다.

2) 주요 통찰:
- 상황의 구조적이고 해석 가능한 표현을 생성하여 LLM이 역할, 행동 및 시공간 맥락을 추론할 수 있도록 합니다.
- 기존 방법보다 최대 20% 더 높은 성능을 보이며, 쿼리 시간의 컨텍스트 토큰을 51% 줄입니다.
- 인간과 유사한 에피소드 기억을 LLM에 부여합니다.

3) GSW는 긴 문서에서 중요한 정보를 효율적으로 추출하고 추론할 수 있게 합니다.

[출처]
- 논문: Beyond Fact Retrieval: Episodic Memory for RAG with Generative Semantic Workspaces
  HuggingFace URL: https://huggingface.co/papers/2511.07587
  저자: Shreyas Rajesh, Pavan Holur, Chenda Duan, David Chong
  Upvote: 8""",
        "expected_title": "Generative Semantic Workspaces",
        "search_type": "paper",
    },
    {
        "question": "GUI-360: A Comprehensive Dataset and Benchmark for Computer-Using Agents",
        "ground_truth": """1) GUI-360은 컴퓨터 사용 에이전트를 위한 대규모 데이터셋과 벤치마크입니다.

2) 주요 통찰:
- 120만 개 이상의 실행된 작업 단계를 포함하여 다양한 Windows 오피스 애플리케이션에서 수집된 데이터로 구성됩니다.
- GUI 그라운딩, 화면 파싱, 행동 예측의 세 가지 주요 작업을 지원합니다.
- 감독 학습과 강화 학습을 통해 성능 향상이 가능합니다.

3) GUI-360은 다양한 GUI 환경에서 에이전트의 성능을 평가하고 훈련할 수 있는 데이터를 제공합니다.

[출처]
- 논문: GUI-360: A Comprehensive Dataset and Benchmark for Computer-Using Agents
  HuggingFace URL: https://huggingface.co/papers/2511.04307
  저자: Jian Mu, Chaoyun Zhang, Chiming Ni, Lu Wang
  Upvote: 14""",
        "expected_title": "GUI-360",
        "search_type": "paper",
    },
    {
        "question": "오디오 기반 애니메이션의 캐릭터 정체성을 유지하는 모델이 있나요?",
        "ground_truth": """1) Lookahead Anchoring은 오디오 기반 휴먼 애니메이션에서 캐릭터 정체성을 유지하는 기법입니다.

2) 주요 통찰:
- 미래의 키프레임을 동적 가이드로 사용하여 입술 동기화, 정체성 유지 및 시각적 품질을 향상시킵니다.
- 캐릭터가 시간에 따라 정체성을 잃는 문제를 해결합니다.
- 키프레임을 생성하는 추가 단계 없이도 자연스러운 움직임을 유지할 수 있습니다.

3) 음성이나 음악에 맞춰 캐릭터를 애니메이션화하면서도 캐릭터의 고유한 특성과 스타일을 보존합니다.

[출처]
- 논문: Lookahead Anchoring: Preserving Character Identity in Audio-Driven Human Animation
  HuggingFace URL: https://huggingface.co/papers/2510.23581
  저자: Junyoung Seo, Rodrigo Mira, Alexandros Haliassos
  Upvote: 41""",
        "expected_title": "Lookahead Anchoring",
        "search_type": "paper",
    },
    {
        "question": "core attention disaggregation 은 무엇인가요?",
        "ground_truth": """1) Core Attention Disaggregation(CAD)은 긴 컨텍스트의 대형 언어 모델 훈련을 개선하는 기술입니다.

2) 주요 통찰:
- 코어 어텐션 계산을 모델의 나머지 부분과 분리하여 별도의 장치 풀에서 실행합니다.
- 코어 어텐션은 상태가 없고 조정 가능한 작업으로 나눌 수 있어 효율적인 스케줄링이 가능합니다.
- DistCA 시스템을 통해 훈련 속도를 최대 1.35배 향상시키고 메모리 사용을 줄입니다.

3) 어텐션 연산을 분해하여 처리함으로써 긴 문맥 언어 모델 학습의 효율성을 높입니다.

[출처]
- 논문: Efficient Long-context Language Model Training by Core Attention Disaggregation
  HuggingFace URL: https://huggingface.co/papers/2510.18121
  저자: Yonghao Zhuang, Junda Chen, Bo Pang, Yi Gu
  Upvote: 121""",
        "expected_title": "Core Attention Disaggregation",
        "search_type": "paper",
    },
    {
        "question": "LLM에서 환각탐지를 할 수 있는 모델에 대해서 알려주세요",
        "ground_truth": """1) FaithLens는 LLM의 환각 탐지를 위한 비용 효율적이고 효과적인 모델입니다.

2) 주요 통찰:
- 고급 LLM을 사용하여 훈련 데이터를 합성하고 규칙 기반 강화 학습을 적용합니다.
- 다양한 작업에서 GPT-4 및 o3보다 우수한 성능을 보입니다.
- 이진 예측과 함께 신뢰성을 높이기 위한 설명을 제공합니다.

3) FaithLens는 생성된 텍스트가 사실에 기반하지 않은 정보를 포함하는지 감지하고 설명합니다.

[출처]
- 논문: FaithLens: Detecting and Explaining Faithfulness Hallucination
  HuggingFace URL: https://huggingface.co/papers/2512.20182""",
        "expected_title": "FaithLens",
        "search_type": "paper",
    },
    {
        "question": "LLM에서 캐시와 관련된 논문이 있나요?",
        "ground_truth": """1) Cache-to-Cache(C2C)는 LLM 간의 직접적인 시맨틱 통신을 가능하게 하는 기법입니다.

2) 주요 통찰:
- LLM들이 텍스트가 아닌 캐시를 통해 직접적으로 의미를 전달할 수 있습니다.
- 기존의 텍스트 기반 통신보다 평균 8.5-10.5% 높은 정확도를 달성합니다.
- 약 2배의 속도 향상을 보여줍니다.

3) KV-캐시를 프로젝션하고 융합하여 LLM 간 효율적인 의미 전송을 가능하게 합니다.

[출처]
- 논문: Cache-to-Cache: Direct Semantic Communication Between Large Language Models
  HuggingFace URL: https://huggingface.co/papers/2510.03215
  GitHub: https://github.com/thu-nics/C2C
  저자: Tianyu Fu, Zihan Min, Hanling Zhang
  Upvote: 97""",
        "expected_title": "Cache-to-Cache",
        "search_type": "paper",
    },
    {
        # 웹 검색으로 넘어가는 질문들 - 정확한 논문 출처보다 답변 품질이 중요
        "question": "rag란 무엇인가?",
        "ground_truth": """1) RAG(Retrieval-Augmented Generation)는 검색 증강 생성 기법입니다.

2) 주요 통찰:
- 외부 지식 베이스에서 관련 정보를 검색하여 LLM의 응답 생성에 활용합니다.
- LLM의 지식을 확장하고 최신 정보를 반영할 수 있습니다.
- 환각(hallucination)을 줄일 수 있습니다.

3) RAG는 검색과 생성을 결합하여 더 정확하고 신뢰할 수 있는 답변을 생성합니다.""",
        "expected_title": None,
        "search_type": "web",
    },
    {
        "question": "langgraph란 무엇인가요?",
        "ground_truth": """1) LangGraph는 AI 에이전트 워크플로우를 구축하고 관리하기 위한 오픈 소스 프레임워크입니다.

2) 주요 통찰:
- 그래프 기반 아키텍처를 사용하여 AI 에이전트 간의 복잡한 관계를 모델링합니다.
- 여러 LLM 에이전트를 효율적으로 정의하고 조정할 수 있는 구조화된 프레임워크를 제공합니다.
- 조건부 분기, 순환, 상태 관리, 체크포인팅 등을 지원합니다.

3) StateGraph를 통해 노드와 엣지로 워크플로우를 정의합니다.""",
        "expected_title": None,
        "search_type": "web",
    },
    {
        "question": "랭체인에 대해서 설명해주세요",
        "ground_truth": """1) LangChain은 LLM 애플리케이션 개발을 위한 프레임워크입니다.

2) 주요 통찰:
- 다양한 데이터 소스와 도구와 연결할 수 있는 모듈을 제공합니다.
- 프롬프트 관리, 체인 구성, 에이전트, 메모리, 문서 로더, 벡터 저장소 등 다양한 컴포넌트를 제공합니다.
- 챗봇, 가상 비서, 맞춤형 질문-응답 시스템 등 생성적 AI 애플리케이션을 쉽게 구축할 수 있습니다.

3) Python과 JavaScript/TypeScript 버전이 있습니다.""",
        "expected_title": None,
        "search_type": "web",
    },
]


def generate_analysis_report(
    results_df: pd.DataFrame,
    output_path: str,
) -> None:
    """
    평가 결과를 분석하여 Markdown 리포트 생성

    Args:
        results_df: 평가 결과 DataFrame
        output_path: 리포트 저장 경로
    """
    from datetime import datetime

    metric_columns = [
        "context_recall",
        "context_precision",
        "faithfulness",
        "answer_relevancy",
        "answer_correctness",
    ]

    # 논문/웹 검색 분리
    paper_df = results_df[results_df["search_type"] == "paper"]
    web_df = results_df[results_df["search_type"] == "web"]

    # 등급 판정 함수
    def get_grade(score: float) -> str:
        if pd.isna(score) or score == 0:
            return "❌ 측정 실패"
        elif score >= 0.9:
            return "✅ 우수"
        elif score >= 0.7:
            return "✅ 양호"
        elif score >= 0.5:
            return "⚠️ 보통"
        else:
            return "❌ 미흡"

    # 점수 범위 계산
    def get_score_range(df: pd.DataFrame, col: str) -> str:
        if col not in df.columns:
            return "N/A"
        valid = df[col].dropna()
        valid = valid[valid > 0]
        if valid.empty:
            return "nan 다수"
        return f"{valid.min():.2f}~{valid.max():.2f}"

    # nan 개수 계산
    def count_nan(df: pd.DataFrame, col: str) -> int:
        if col not in df.columns:
            return 0
        return df[col].isna().sum() + (df[col] == 0).sum()

    # 리포트 생성
    report = f"""# RAGAS 평가 결과 분석

> 생성일시: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

## 전체 평가

| 항목 | 상태 | 설명 |
|------|------|------|
"""

    # 예상 논문 정확도
    if not paper_df.empty:
        title_found_count = int(paper_df["title_found"].sum())
        title_total = len(paper_df)
        title_accuracy = title_found_count / title_total * 100
        title_status = "매우 좋음" if title_accuracy >= 80 else ("좋음" if title_accuracy >= 60 else "개선 필요")
        report += f"| 예상 논문 정확도 | {title_accuracy:.1f}% ({title_found_count}/{title_total}) | {title_status} |\n"

    # 각 지표 요약
    for metric in metric_columns:
        if metric in results_df.columns:
            score_range = get_score_range(results_df, metric)
            nan_count = count_nan(results_df, metric)
            mean_score = results_df[metric].mean()

            if nan_count > len(results_df) / 2:
                status = "문제"
                desc = f"nan {nan_count}개 발생"
            else:
                status = get_grade(mean_score).split(" ")[0]
                desc = get_grade(mean_score).split(" ")[1] if " " in get_grade(mean_score) else ""

            report += f"| {metric} | {score_range} | {status} {desc} |\n"

    report += """
---

## 각 지표 설명

"""

    # 지표별 상세 설명
    metric_info = {
        "context_recall": {
            "name": "Context Recall",
            "meaning": "검색된 문서가 정답에 필요한 정보를 얼마나 포함하는지",
            "good_score": "0.8+",
        },
        "context_precision": {
            "name": "Context Precision",
            "meaning": "검색된 문서 중 실제로 관련 있는 문서 비율",
            "good_score": "0.8+",
        },
        "faithfulness": {
            "name": "Faithfulness",
            "meaning": "답변이 컨텍스트에만 기반하는지 (환각 여부)",
            "good_score": "0.9+",
        },
        "answer_relevancy": {
            "name": "Answer Relevancy",
            "meaning": "답변이 질문과 얼마나 관련 있는지",
            "good_score": "0.7+",
        },
        "answer_correctness": {
            "name": "Answer Correctness",
            "meaning": "답변이 정답(Ground Truth)과 얼마나 일치하는지",
            "good_score": "0.7+",
        },
    }

    for metric, info in metric_info.items():
        if metric in results_df.columns:
            score_range = get_score_range(results_df, metric)
            mean_score = results_df[metric].mean()
            grade = get_grade(mean_score)

            report += f"""### {info["name"]}
- **의미**: {info["meaning"]}
- **좋은 점수**: {info["good_score"]}
- **현재 결과**: {score_range} {grade}

"""

    report += """---

## 해석

### 좋은 점
"""

    # 좋은 점 자동 분석
    good_points = []
    if "faithfulness" in results_df.columns:
        faith_mean = results_df["faithfulness"].mean()
        if faith_mean >= 0.9:
            good_points.append(f"- **Faithfulness {faith_mean:.2f}** → RAG가 환각 없이 문서 기반으로 답변")

    if "context_recall" in results_df.columns:
        recall_mean = results_df["context_recall"].mean()
        if recall_mean >= 0.5:
            good_points.append(f"- **Context Recall {recall_mean:.2f}** → 관련 문서를 잘 검색함")

    if "context_precision" in results_df.columns:
        prec_mean = results_df["context_precision"].mean()
        if prec_mean >= 0.7:
            good_points.append(f"- **Context Precision {prec_mean:.2f}** → 검색된 문서의 관련성이 높음")

    if not paper_df.empty:
        title_accuracy = paper_df["title_found"].sum() / len(paper_df) * 100
        if title_accuracy >= 70:
            good_points.append(f"- **예상 논문 {title_accuracy:.1f}% 정확도** → 원하는 논문을 잘 찾음")

    if good_points:
        report += "\n".join(good_points) + "\n"
    else:
        report += "- 분석 중...\n"

    report += """
### 문제점
"""

    # 문제점 자동 분석
    bad_points = []
    total_nan = 0
    for metric in metric_columns:
        if metric in results_df.columns:
            nan_count = count_nan(results_df, metric)
            total_nan += nan_count

    if total_nan > 0:
        bad_points.append(f"- **nan 값 {total_nan}개** → RAGAS 내부 처리 오류 (긴 텍스트, API 타임아웃 등)")

    if "answer_relevancy" in results_df.columns:
        relevancy_mean = results_df["answer_relevancy"].mean()
        if relevancy_mean < 0.7:
            bad_points.append(f"- **Answer Relevancy {relevancy_mean:.2f}** → 답변과 질문의 관련성 개선 필요")

    if "answer_correctness" in results_df.columns:
        correctness_mean = results_df["answer_correctness"].mean()
        if correctness_mean < 0.5 or count_nan(results_df, "answer_correctness") > len(results_df) / 2:
            bad_points.append("- **Answer Correctness** → 측정 실패 또는 낮은 점수")

    if not web_df.empty:
        web_nan_count = sum(count_nan(web_df, m) for m in metric_columns if m in web_df.columns)
        if web_nan_count > len(web_df) * 2:
            bad_points.append("- **웹 검색 결과** → 대부분의 지표가 nan")

    if bad_points:
        report += "\n".join(bad_points) + "\n"
    else:
        report += "- 특별한 문제 없음\n"

    report += """
---

## 점수 기준표

| 등급 | 점수 범위 | 의미 |
|------|----------|------|
| 우수 | 0.9 ~ 1.0 | 매우 좋음 |
| 양호 | 0.7 ~ 0.9 | 좋음 |
| 보통 | 0.5 ~ 0.7 | 개선 필요 |
| 미흡 | 0.0 ~ 0.5 | 문제 있음 |

---

## 상세 결과

### 전체 평균
"""

    for metric in metric_columns:
        if metric in results_df.columns:
            mean_score = results_df[metric].mean()
            report += f"- {metric}: **{mean_score:.4f}**\n"

    if not paper_df.empty:
        report += f"""
### 논문 검색 ({len(paper_df)}개)
"""
        for metric in metric_columns:
            if metric in paper_df.columns:
                mean_score = paper_df[metric].mean()
                report += f"- {metric}: **{mean_score:.4f}**\n"

        title_accuracy = paper_df["title_found"].sum() / len(paper_df) * 100
        report += f"- 예상 논문 정확도: **{title_accuracy:.1f}%** ({int(paper_df['title_found'].sum())}/{len(paper_df)})\n"

    if not web_df.empty:
        report += f"""
### 웹 검색 ({len(web_df)}개)
"""
        for metric in metric_columns:
            if metric in web_df.columns:
                mean_score = web_df[metric].mean()
                report += f"- {metric}: **{mean_score:.4f}**\n"

    report += """
---

## 개선 방향

"""

    # 개선 방향 자동 생성
    improvements = []
    if total_nan > 0:
        improvements.append("""1. **nan 문제 해결**
   - 텍스트 길이 추가 제한
   - API 타임아웃 증가
   - 웹 검색 질문에 대한 별도 처리""")

    if "answer_relevancy" in results_df.columns and results_df["answer_relevancy"].mean() < 0.7:
        improvements.append("""2. **Answer Relevancy 개선**
   - 프롬프트 최적화
   - 답변 형식 간소화""")

    if not web_df.empty:
        improvements.append("""3. **웹 검색 평가 방식 개선**
   - 웹 검색용 별도 ground truth 작성
   - 또는 웹 검색 질문은 평가에서 제외""")

    if improvements:
        report += "\n\n".join(improvements) + "\n"
    else:
        report += "- 현재 결과가 양호하여 특별한 개선 사항 없음\n"

    # 파일 저장
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"[SUCCESS] 분석 리포트가 '{output_path}' 파일에 저장되었습니다!")


def run_ragas_evaluation(
    evaluation_data: List[Dict[str, str]] = None,
    output_path: str = None,
    verbose: bool = True,
) -> pd.DataFrame:
    """
    RAGAS 평가 실행

    Args:
        evaluation_data: 평가 데이터 리스트 (question, ground_truth 포함)
        output_path: 결과 저장 경로 (None이면 기본 경로)
        verbose: 상세 출력 여부

    Returns:
        평가 결과 DataFrame
    """
    if evaluation_data is None:
        evaluation_data = EVALUATION_DATASET

    if output_path is None:
        output_path = str(PROJECT_ROOT / "output" / "ragas_evaluation_results.csv")

    # 출력 디렉토리 생성
    output_dir = Path(output_path).parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # RAGAS용 임베딩 래퍼 생성
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    ragas_embeddings = LangchainEmbeddingsWrapper(embeddings=embeddings)

    # RAGAS용 LLM (타임아웃 증가)
    ragas_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, request_timeout=120)

    # 텍스트 길이 제한 (nan 방지)
    MAX_CONTEXT_LENGTH = 2000  # 각 context 최대 길이
    MAX_ANSWER_LENGTH = 3000   # answer 최대 길이
    MAX_GROUND_TRUTH_LENGTH = 2000  # ground_truth 최대 길이

    def truncate_text(text: str, max_length: int) -> str:
        """텍스트 길이 제한"""
        if len(text) > max_length:
            return text[:max_length] + "..."
        return text

    # 평가 데이터 수집
    questions = []
    answers = []
    contexts_list = []
    ground_truths = []
    expected_titles = []
    search_types = []
    title_found_list = []  # 예상 논문이 실제로 검색되었는지

    print("\n" + "=" * 60)
    print("RAGAS 평가 시작")
    print("=" * 60)
    print(f"총 {len(evaluation_data)}개 질문 평가 예정\n")

    for i, data in enumerate(evaluation_data, 1):
        query = data["question"]
        ground_truth = data["ground_truth"]
        expected_title = data.get("expected_title")
        search_type = data.get("search_type", "paper")

        if verbose:
            print(f"\n[{i}/{len(evaluation_data)}] 질문: {query[:50]}...")
            if expected_title:
                print(f"  예상 논문: {expected_title}")

        # RAG 시스템으로 답변 생성
        result = evaluate_rag_system.ask_question(query, verbose=False)

        if result["success"]:
            answer_text = result["answer"]
            sources = result.get("sources", [])
            # 실제 RAG 시스템이 사용한 context 가져오기
            contexts = result.get("contexts", [])

            # RAGAS 평가를 위해 answer + sources 합치기
            answer = answer_text
            if sources:
                answer += "\n\n[출처]"
                for source in sources:
                    if source.get("type") == "paper":
                        answer += f"\n- 논문: {source.get('title', 'Unknown')}"
                        answer += f"\n  HuggingFace URL: {source.get('huggingface_url', 'N/A')}"
                        if source.get("github_url"):
                            answer += f"\n  GitHub: {source.get('github_url')}"
                        answer += f"\n  저자: {source.get('authors', 'Unknown')}"
                        answer += f"\n  Upvote: {source.get('upvote', 0)}"
                    else:
                        answer += f"\n- 웹: {source.get('title', 'Unknown')}"
                        answer += f"\n  URL: {source.get('url', 'N/A')}"

            if verbose:
                print(f"  답변 생성 완료 (길이: {len(answer_text)}자)")
                print(f"  출처 개수: {len(sources)}개")
                print(f"  실제 사용된 컨텍스트: {len(contexts)}개")
                print(f"  평가용 답변 길이: {len(answer)}자 (출처 포함)")

            # 예상 논문 제목이 출처에 있는지 확인
            title_found = False
            if expected_title and sources:
                # 공백/줄바꿈 정규화 함수
                def normalize_text(text: str) -> str:
                    return re.sub(r'\s+', ' ', text.strip().lower())

                expected_normalized = normalize_text(expected_title)
                for source in sources:
                    source_title = source.get("title", "")
                    source_normalized = normalize_text(source_title)
                    if expected_normalized in source_normalized:
                        title_found = True
                        if verbose:
                            print(f"  [O] 예상 논문 발견: {source_title}")
                        break
                if not title_found and verbose:
                    print(f"  [X] 예상 논문 미발견")
                    for source in sources:
                        print(f"      - {source.get('title', 'Unknown')[:60]}")
            elif search_type == "web":
                title_found = True  # 웹 검색은 항상 True (논문 검색 아님)
                if verbose:
                    print(f"  [웹검색] 논문 검색 대상 아님")
        else:
            answer = f"답변 생성 실패: {result.get('error', 'Unknown error')}"
            contexts = []
            title_found = False
            if verbose:
                print(f"  [ERROR] {answer}")

        # 데이터 수집 (텍스트 길이 제한 적용)
        questions.append(query)

        # answer 길이 제한
        truncated_answer = truncate_text(answer, MAX_ANSWER_LENGTH)
        answers.append(truncated_answer)

        # contexts 길이 제한 및 빈 값 방지
        if contexts:
            truncated_contexts = [truncate_text(ctx, MAX_CONTEXT_LENGTH) for ctx in contexts]
        else:
            truncated_contexts = ["관련 문서를 찾지 못했습니다."]
        contexts_list.append(truncated_contexts)

        # ground_truth 길이 제한
        truncated_ground_truth = truncate_text(ground_truth, MAX_GROUND_TRUTH_LENGTH)
        ground_truths.append(truncated_ground_truth)

        expected_titles.append(expected_title if expected_title else "")
        search_types.append(search_type)
        title_found_list.append(title_found)

    # RAGAS Dataset 생성
    print("\n" + "=" * 60)
    print("[RAGAS] 데이터셋 생성 중...")
    print("=" * 60)

    # nan 방지를 위한 데이터 검증
    for i in range(len(questions)):
        if not answers[i] or answers[i].strip() == "":
            answers[i] = "답변을 생성할 수 없습니다."
        if not contexts_list[i] or len(contexts_list[i]) == 0:
            contexts_list[i] = ["관련 문서를 찾지 못했습니다."]
        if not ground_truths[i] or ground_truths[i].strip() == "":
            ground_truths[i] = "정답 정보가 없습니다."

    dataset_dict = {
        "question": questions,
        "answer": answers,
        "contexts": contexts_list,
        "ground_truth": ground_truths,  # Context Recall, Precision, Answer Correctness에 필요
    }

    # 데이터 확인
    print(f"  Questions: {len(questions)}개")
    print(f"  Answers: {len(answers)}개")
    print(f"  Contexts: {len(contexts_list)}개")
    print(f"  Ground Truths: {len(ground_truths)}개")

    dataset = Dataset.from_dict(dataset_dict)

    # RAGAS 평가 실행
    print("\n[RAGAS] 평가 실행 중... (시간이 걸릴 수 있습니다)")
    print("평가 지표: Context Recall, Context Precision, Faithfulness, Answer Relevancy, Answer Correctness")

    try:
        result = evaluate(
            dataset=dataset,
            metrics=[
                context_recall,  # 검색된 컨텍스트가 ground truth를 얼마나 포함하는지
                context_precision,  # 검색된 컨텍스트 중 관련 있는 것의 비율
                faithfulness,  # 답변이 컨텍스트에 기반하는지 (할루시네이션 방지)
                answer_relevancy,  # 답변이 질문과 관련이 있는지
                answer_correctness,  # 답변이 ground truth와 얼마나 일치하는지
            ],
            llm=ragas_llm,
            embeddings=ragas_embeddings,
        )

        # 결과를 DataFrame으로 변환
        results_df = result.to_pandas()

        # nan 값을 0으로 대체 (평가 실패한 경우)
        metric_cols = ["context_recall", "context_precision", "faithfulness", "answer_relevancy", "answer_correctness"]
        for col in metric_cols:
            if col in results_df.columns:
                nan_count = results_df[col].isna().sum()
                if nan_count > 0:
                    print(f"  [WARN] {col}: {nan_count}개 nan 값 → 0으로 대체")
                results_df[col] = results_df[col].fillna(0)

        # 추가 정보 추가
        results_df["question"] = questions
        results_df["answer"] = answers
        results_df["ground_truth"] = ground_truths
        results_df["expected_title"] = expected_titles
        results_df["search_type"] = search_types
        results_df["title_found"] = title_found_list

        # 컬럼 순서 재정렬
        column_order = [
            "question",
            "expected_title",
            "search_type",
            "title_found",
            "answer",
            "ground_truth",
            "context_recall",
            "context_precision",
            "faithfulness",
            "answer_relevancy",
            "answer_correctness",
        ]
        available_columns = [col for col in column_order if col in results_df.columns]
        results_df = results_df[available_columns]

        # 상세 결과 CSV 저장
        results_df.to_csv(
            output_path,
            index=False,
            encoding="utf-8-sig",
            quoting=csv.QUOTE_ALL,
            escapechar="\\",
            lineterminator="\n",
        )

        print(f"\n[SUCCESS] 상세 결과가 '{output_path}' 파일에 저장되었습니다!")
        print(f"총 {len(results_df)}개의 질문이 평가되었습니다.")

        # ===== 요약 지표 계산 및 저장 =====
        metric_columns = [
            "context_recall",
            "context_precision",
            "faithfulness",
            "answer_relevancy",
            "answer_correctness",
        ]

        # 요약 데이터 생성
        summary_data = []

        # 전체 평균
        for metric in metric_columns:
            if metric in results_df.columns:
                mean_score = results_df[metric].mean()
                min_score = results_df[metric].min()
                max_score = results_df[metric].max()
                std_score = results_df[metric].std()
                summary_data.append({
                    "metric": metric,
                    "category": "전체",
                    "mean": mean_score,
                    "min": min_score,
                    "max": max_score,
                    "std": std_score,
                    "count": len(results_df),
                })

        # 논문 검색 (paper)만 필터링
        paper_df = results_df[results_df["search_type"] == "paper"]
        if not paper_df.empty:
            for metric in metric_columns:
                if metric in paper_df.columns:
                    mean_score = paper_df[metric].mean()
                    min_score = paper_df[metric].min()
                    max_score = paper_df[metric].max()
                    std_score = paper_df[metric].std()
                    summary_data.append({
                        "metric": metric,
                        "category": "논문검색",
                        "mean": mean_score,
                        "min": min_score,
                        "max": max_score,
                        "std": std_score,
                        "count": len(paper_df),
                    })

        # 웹 검색 (web)만 필터링
        web_df = results_df[results_df["search_type"] == "web"]
        if not web_df.empty:
            for metric in metric_columns:
                if metric in web_df.columns:
                    mean_score = web_df[metric].mean()
                    min_score = web_df[metric].min()
                    max_score = web_df[metric].max()
                    std_score = web_df[metric].std()
                    summary_data.append({
                        "metric": metric,
                        "category": "웹검색",
                        "mean": mean_score,
                        "min": min_score,
                        "max": max_score,
                        "std": std_score,
                        "count": len(web_df),
                    })

        # 논문 검색 정확도 (title_found)
        if not paper_df.empty:
            title_accuracy = paper_df["title_found"].sum() / len(paper_df)
            summary_data.append({
                "metric": "title_found_accuracy",
                "category": "논문검색",
                "mean": title_accuracy,
                "min": 0,
                "max": 1,
                "std": 0,
                "count": len(paper_df),
            })

        # 요약 DataFrame 생성 및 저장
        summary_df = pd.DataFrame(summary_data)
        summary_path = output_path.replace(".csv", "_summary.csv")
        summary_df.to_csv(
            summary_path,
            index=False,
            encoding="utf-8-sig",
        )

        print(f"[SUCCESS] 요약 지표가 '{summary_path}' 파일에 저장되었습니다!")

        # 분석 리포트 자동 생성
        analysis_path = output_path.replace(".csv", "_analysis.md")
        generate_analysis_report(results_df, analysis_path)

        # 터미널에 요약 출력
        print("\n" + "=" * 60)
        print("평가 결과 요약")
        print("=" * 60)

        print("\n[전체 평균]")
        for metric in metric_columns:
            if metric in results_df.columns:
                mean_score = results_df[metric].mean()
                print(f"  {metric}: {mean_score:.4f}")

        if not paper_df.empty:
            print(f"\n[논문 검색] ({len(paper_df)}개)")
            for metric in metric_columns:
                if metric in paper_df.columns:
                    mean_score = paper_df[metric].mean()
                    print(f"  {metric}: {mean_score:.4f}")
            title_accuracy = paper_df["title_found"].sum() / len(paper_df) * 100
            print(f"  예상 논문 정확도: {title_accuracy:.1f}% ({int(paper_df['title_found'].sum())}/{len(paper_df)})")

        if not web_df.empty:
            print(f"\n[웹 검색] ({len(web_df)}개)")
            for metric in metric_columns:
                if metric in web_df.columns:
                    mean_score = web_df[metric].mean()
                    print(f"  {metric}: {mean_score:.4f}")

        return results_df

    except Exception as e:
        print(f"\n[ERROR] RAGAS 평가 실패: {e}")
        import traceback

        traceback.print_exc()
        return pd.DataFrame()


def main():
    """메인 실행 함수"""
    print("\n" + "=" * 60)
    print("RAG 시스템 RAGAS 평가")
    print("=" * 60)

    # RAG 시스템 초기화
    print("\n[INIT] RAG 시스템 초기화 중...")
    init_result = evaluate_rag_system.initialize_rag_system(
        model_name="text-embedding-3-small",
        llm_model="gpt-4o-mini",
        llm_temperature=0,
        use_reranker=True,
        reranker_type="cross-encoder",
    )

    if init_result["status"] != "success":
        print(f"[ERROR] RAG 시스템 초기화 실패: {init_result['message']}")
        return

    # 시스템 상태 확인
    status = evaluate_rag_system.get_system_status()
    print("\n[시스템 상태]")
    for key, value in status.items():
        print(f"  {key}: {'O' if value else 'X'}")

    # 모듈 변수 확인
    print("\n[모듈 변수 확인]")
    print(f"  _vectorstore: {'O' if evaluate_rag_system._vectorstore is not None else 'X'}")
    print(f"  _bm25_retriever: {'O' if evaluate_rag_system._bm25_retriever is not None else 'X'}")
    print(f"  _llm: {'O' if evaluate_rag_system._llm is not None else 'X'}")

    # RAGAS 평가 실행
    results_df = run_ragas_evaluation(verbose=True)

    # 개별 결과 출력
    if not results_df.empty:
        print("\n" + "=" * 60)
        print("개별 평가 결과")
        print("=" * 60)
        for idx, row in results_df.iterrows():
            search_type = row.get("search_type", "paper")
            title_found = row.get("title_found", False)
            expected_title = row.get("expected_title", "")

            print(f"\n[{idx + 1}] {row['question'][:60]}...")
            print(f"    검색 유형: {search_type}")
            if expected_title:
                status = "O" if title_found else "X"
                print(f"    예상 논문: {expected_title} [{status}]")
            print(f"    Context Recall: {row.get('context_recall', 0):.4f}")
            print(f"    Context Precision: {row.get('context_precision', 0):.4f}")
            print(f"    Faithfulness: {row.get('faithfulness', 0):.4f}")
            print(f"    Answer Relevancy: {row.get('answer_relevancy', 0):.4f}")
            print(f"    Answer Correctness: {row.get('answer_correctness', 0):.4f}")


if __name__ == "__main__":
    main()

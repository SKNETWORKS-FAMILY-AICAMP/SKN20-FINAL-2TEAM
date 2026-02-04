import base64
import os
from pathlib import Path

import chromadb
import clip
import torch
from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from PIL import Image

load_dotenv()
import os
if not os.environ.get('OPENAI_API_KEY'):
    raise ValueError('OPENAI_API_KEY 없음 .env 확인!')

"""
RAG (Retrieval-Augmented Generation) 체인

    [입력 이미지] 
        ↓
    [VLM 분석] ← GPT-4O
        ↓
    [구조화된 설명 생성] (json)
        ↓
    [CLIP 벡터 검색] → 유사 디자인 N개 추출 -> 필터링: 자신의 도면 제거 + 출원번호별 1개
        ↓
    [각 유사 디자인 VLM 분석]
        ↓
    [비교 분석 LLM]
        ↓
    [상세 리포트 생성]
"""

# ChromaDB 클라이언트 초기화
chroma_client = chromadb.PersistentClient(path="./chroma_db")

#생성할때와 동일한 이름으로 컬렉션 불러오기
image_collection = chroma_client.get_collection(name="design")

"""
입력 이미지 분석 chain
"""
llm = ChatOpenAI(model="gpt-4o", temperature=0)
output_parser = StrOutputParser()

# 도면 이미지 분석 프롬프트
'''
FEW_SHOT_CAPTIONING = """
당신의 임무: 제품 도면의 시각적 특징을 객관적으로 분석하세요.

출력 형식: JSON으로 제품의 형상, 형태, 실루엣, 기능적 디자인을 객관적으로 기술하세요.
(어떤 구조를 강제하지 않고, 도면에 맞게 기술하세요)

<example1>
분석 결과:
{{
  "물품": "화장품 용기",
  "주요 특징": [
    "상단과 하단의 폭이 용기의 중간 부분보다 넓은 구조",
    "용기의 상단과 하단의 연결부분이 자연스러운 곡면형태로 이루어있는 점",
    "용기의 몸체의 중간 부분에서 하단 부분으로 홈이 형성되어 있는 점",
    "용기의 밑 부분이 뭉퉁한 곡면이 있는 점"
  ]
}}
</example1>

<example2>
분석 결과:
{{
  "물품": "원통형 용기",
  "주요 특징": [
    "몸체의 상부 뚜껑 결합부분이 원형",
    "뚜껑 결합부분에 나사산이 1개 형성되어 회전하여 뚜껑을 열고 닫을 수 있는 점",
    "몸체의 상부 뚜껑 결합부분이 지름이 작은 원형",
    "하부는 상부보다 지름이 큰 원형인 점"
  ]
}}
</example2>

<example3>
분석 결과:
{{
    "물품": "브러시",
    "주요 특징": [
        "브러쉬 최하단의 돌출 모양의 골에서 마감 형성",
        "전체적으로 둥근 미감을 형성",
        "브러시 측면이 물결 모양의 3개의 돌출 형상"
    ]
}}
</example3>


이제 아래 이미지를 분석하세요. 실제 제품의 형태를 정확히 관찰하고 기술하세요:
"""
'''

FEW_SHOT_CAPTIONING = """
당신의 임무는 제품 도면 이미지를 보고,
'실제로 도면에서 관찰되는 형상 요소'만을 단계적으로 기록하는 것입니다.

⚠️ 중요 규칙
- 비교, 평가, 유사/비유사 판단을 하지 마십시오.
- 일반적인 제품 특성이나 추측을 작성하지 마십시오.
- 도면에 명확히 보이지 않는 요소는 "관찰되지 않음"이라고 명시하십시오.
- 표현은 객관적 형상 중심으로 작성하십시오.

아래 사고 단계를 반드시 순서대로 수행하십시오.

[사고 단계]
1단계: 전체 실루엣을 관찰한다.
2단계: 몸체 형태를 관찰한다.
3단계: 상부(캡/결합부) 구조를 관찰한다.
4단계: 하부 형태를 관찰한다.
5단계: 전체 비례 관계를 관찰한다.

출력 형식은 반드시 다음 JSON을 따르십시오.

{{
  "물품": "...",
  "형상_관찰": {{
    "전체_실루엣": "...",
    "몸체_형태": "...",
    "상부_구조": "...",
    "하부_형태": "...",
    "비례_관계": "..."
  }}
}}

이제 아래 이미지를 분석하십시오.
"""

# 프롬프트 템플릿 정의
prompt = ChatPromptTemplate.from_messages([
    ("system", "당신은 화장품 도면 분석가입니다. 주어진 제품 도면 이미지를 분석해 JSON 형식으로 설명합니다."),
    ("user", [
        {"type": "text", "text": FEW_SHOT_CAPTIONING},
        {"type": "image_url", "image_url": {"url": "{image_url}"}}
    ])
])

# 이미지를 base64로 인코딩하여 data URL 생성
image_path = r"data/images/3020250027386-09-01-1_001.jpg"
with open(image_path, "rb") as f:
    base64_image = base64.b64encode(f.read()).decode('utf-8')
url = f"data:image/jpeg;base64,{base64_image}"

# 체인 생성 및 실행
chain = prompt | llm | output_parser
result = chain.invoke({"image_url": url}) #입력 디자인 분석 결과 
print("입력 이미지 분석 결과:\n", result)

"""
입력 이미지 임베딩 / 벡터 검색 chain
"""

# CLIP 모델 로드 (ViT-B/32)
print("CLIP 모델 로드 중...")
device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)
print("CLIP 모델 로드 완료!")

def get_image_embedding(image_path):
    """이미지 파일 경로 -> CLIP 임베딩 벡터 반환"""
    try:
        image = preprocess(Image.open(image_path)).unsqueeze(0).to(device)
        with torch.no_grad():
            embedding = model.encode_image(image) #이미지 임베딩
            embedding = embedding.cpu().numpy()[0].tolist() 
        return embedding
    except Exception as e:
        return None

# 입력 이미지 임베딩 벡터 생성
query_embedding = get_image_embedding(image_path)

# 벡터DB에서 상위 10개 유사 도면 검색
results = image_collection.query(
    query_embeddings=[query_embedding],
    n_results=10
)

# 입력 이미지의 출원번호 추출
input_filename = Path(image_path).stem
input_application_number = input_filename.split('-')[0]

# 필터링: 
# 1. 자신의 도면 제거 (출원번호 같고 거리 0)
# 2. 같은 출원번호 중 가장 유사도 거리가 짧은 것만 유지
filtered_data = {}
for i in range(len(results["ids"][0])):
    design_id = results["ids"][0][i]
    distance = results["distances"][0][i]
    metadata = results["metadatas"][0][i]
    app_number = metadata.get('applicationNumber', 'N/A')
    
    # 자신의 도면 제거
    if app_number == input_application_number and distance == 0:
        continue
    
    # 같은 출원번호 중 가장 거리가 짧은 것만 유지
    if app_number not in filtered_data or distance < filtered_data[app_number]['distance']:
        filtered_data[app_number] = {
            'id': design_id,
            'distance': distance,
            'metadata': metadata
        }

# 필터링된 결과로 변환
results["ids"] = [[item['id'] for item in filtered_data.values()]]
results["distances"] = [[item['distance'] for item in filtered_data.values()]]
results["metadatas"] = [[item['metadata'] for item in filtered_data.values()]]


COMPARE_FEW_SHOT = """
당신은 대한민국 특허청 디자인 심사관의 판단 기준을 설명하는
FTO(Freedom To Operate) 보조 어시스턴트입니다.

아래에는 두 디자인 도면에 대한 '형상 관찰 결과'가 주어집니다.
이를 바탕으로 형상, 실루엣, 전체 형태 측면에서만 비교하십시오.

⚠️ 중요 규칙
- 기능, 재질, 사용 용도는 고려하지 마십시오.
- 억지로 유사하다고 판단하지 마십시오.
- 차이가 더 명확한 경우, 비유사점을 중심으로 작성하십시오.

아래 사고 단계를 반드시 순서대로 수행하십시오.

[사고 단계]
1단계: 전체 실루엣, 상부 구조, 몸체 형태, 비례 중
        가장 차이가 큰 항목 하나를 먼저 선택한다.
2단계: 선택한 항목에서의 구체적인 차이를 서술한다.
3단계: 구조적으로 불가피한 공통 요소만 유사점으로 정리한다.

출력 형식:

{{
  "유사한_점": [
    {{"항목": "...", "설명": "..."}},
    {{"항목": "...", "설명": "..."}}
  ],
  "비유사한_점": [
    {{"항목": "...", "설명": "..."}},
    {{"항목": "...", "설명": "..."}}
  ]
}}

이제 두 디자인을 비교 분석하십시오.
"""


# 프롬프트 템플릿 정의
compare_prompt_template = ChatPromptTemplate.from_messages([
    ("system", """
     당신은 대한민국 특허청 디자인 심사관의 판단 기준을 설명해주는 FTO(Freedom To Operate) 보조 어시스턴트이다.
     당신의 임무는 두 디자인(출원디자인, 비교디자인)을 특허청 심사 과정에서 ‘유사하다고 지적될 수 있는 시각적 공통 요소’만을
    객관적으로 정리하여 설명하는 것이다.
     """),
    ("user", "{comparison_input}")
])

compare_chain = compare_prompt_template | llm | output_parser

print("\n각 유사 디자인 분석 및 비교 분석 진행 중...\n")

comparison_results = []
for i in range(len(results["ids"][0])):
    design_id = results["ids"][0][i]
    distance = results["distances"][0][i]
    metadata = results["metadatas"][0][i]
    
    # 각 유사 디자인 VLM 분석
    similar_image_path = metadata.get('imagePath', 'N/A')
    similar_analysis = ""
    
    if similar_image_path != 'N/A' and os.path.exists(similar_image_path):
        try:
            with open(similar_image_path, "rb") as f:
                similar_base64 = base64.b64encode(f.read()).decode('utf-8')
            similar_url = f"data:image/jpeg;base64,{similar_base64}"
            
            # 같은 프롬프트(FEW_SHOT_CAPTIONING)로 분석
            similar_chain = prompt | llm | output_parser
            similar_analysis = similar_chain.invoke({"image_url": similar_url})
        except Exception as e:
            similar_analysis = f"분석 실패: {e}"
    
    # 비교 분석 입력 생성
    comparison_input = f"""{COMPARE_FEW_SHOT}

    [입력디자인 분석 결과]
    {result}

    [비교디자인 분석 결과 (출원번호: {metadata.get('applicationNumber', 'N/A')})]
    {similar_analysis}
    """
        
    # 비교 분석 실행
    comparison_analysis = compare_chain.invoke({"comparison_input": comparison_input})
    
    comparison_results.append({
        'index': i + 1,
        'design_id': design_id,
        'distance': distance,
        'application_number': metadata.get('applicationNumber', 'N/A'),
        'article_name': metadata.get('articleName', 'N/A'),
        'admst_stat': metadata.get('admstStat', 'N/A'),
        'image_path': similar_image_path,
        'vlm_analysis': similar_analysis,
        'comparison_analysis': comparison_analysis
    })

"""
상세 리포트 생성
"""
final_report = "\n" + "="*70 + "\n"
final_report += "디자인 FTO(Freedom To Operate) 비교 분석 리포트\n"
final_report += "="*70 + "\n\n"

final_report += f"[입력 디자인 (출원번호: {input_application_number})]\n"
final_report += f"{result}\n\n"

for comp in comparison_results:
    final_report += "-"*70 + "\n"
    final_report += f"[비교 대상 {comp['index']}]\n"
    final_report += f"출원번호: {comp['application_number']}\n"
    final_report += f"상품명: {comp['article_name']}\n"
    final_report += f"유사도 거리: {comp['distance']:.4f}\n"
    final_report += f"상태: {comp['admst_stat']}\n"
    final_report += f"이미지 경로: {comp['image_path']}\n\n"
    
    final_report += f"[VLM 분석]\n{comp['vlm_analysis']}\n\n"
    final_report += f"[특허청 심사 기준 유사성 분석]\n{comp['comparison_analysis']}\n\n"

final_report += "="*70 + "\n"
print(final_report)
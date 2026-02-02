from PIL import Image
import torch
import torchvision.transforms as transforms
from torchvision.models import resnet50
import numpy as np
import os
import pickle  

'''
img_emd.py 파일: resnet 모델을 사용해 이미지-> 임베딩 벡터 변환.

문제점: RAG가 답변할때 참고해서 답변할 만한 자연어 정보가 없음

해결: 메터데이터 추가

모든 이미지는 다음과 같은 JSON 객체로 표현된다. 
{
  "embedding": [0.021, -0.13, ...],
  "metadata": {
    "id": "00297",
    "era": "2019",
    "style": "normcore",
    "gender": "women",
    "url": "T_00297_19_normcore_W.jpg",
  }
}

리트리버 유사도 검색은 <임베딩 벡터>로 하고, 그렇게 찾은 사진의 <메타데이터>를 이용해서 RAG가 답변한다. 



'''
# 프로토타입 단계: Sample data 중 woman 이미지만 사용(총 25장)
base_path = r'C:\Users\playdata2\Desktop\Sample\Sample\01.원천데이터'
image_paths = []

# training과 test 폴더에서 woman 이미지 찾기
for folder in ['1.training', '3.test']:
    woman_path = os.path.join(base_path, folder, 'woman')
    if os.path.exists(woman_path):
        # woman 폴더 의 모든 연도 폴더에서 이미지 수집
        for root, dirs, files in os.walk(woman_path):
            for file in files:
                if file.lower().endswith(('.jpg', '.jpeg', '.png')):
                    image_paths.append(os.path.join(root, file))

print(f"총 발견된 이미지: {len(image_paths)}개\n") #25개



def metadata(filename) -> dict:
    """파일명에서 메타데이터 추출 후 dict로 반환

    EX) T_00297_19_normcore_W.jpg
        id: 00297
        era: 2019
        style: normcore
        gender: women
        url: T_00297_19_normcore_W.jpg

    """
    
    filename_1 = os.path.splitext(filename)[0] #확장자(.jpg) 제거
    parts = filename_1.split('_') #_ 기준 분리
    
    metadata = {
        'id': 'unknown',
        'era': 'unknown',
        'style': 'unknown',
        'gender': 'unknown',
        'url': filename
    }
    
    # id 추가
    metadata['id'] = parts[1] 
    
    # 연도 추가
    year = int(parts[2])
    if year >= 50: #1900s
        metadata['era'] = str(1900 + year)
    else: #2000s
        metadata['era'] = str(2000 + year)
    
    # 스타일 추가
    metadata['style'] = parts[3] 
    
    # 성별 추가
    gender_code = parts[4]
    metadata['gender'] = 'women' if gender_code == 'W' else 'men'

    
    return metadata


def embedding(image_path):
    """resnet 모델을 사용해, 이미지를 임베딩 벡터로 변환

       임베딩 벡터 shape: (2048,)
    """

    # resnet 모델 로드
    model = resnet50(pretrained=True)
    model = torch.nn.Sequential(*list(model.children())[:-1])  # 마지막 분류층 제거(특징 추출만 필요하므로)
    model.eval()

    # 이미지 전처리 파이프라인 
    # RESNET 표준 방법 (RESNET 모델을 사용할 때 권장되는 전처리 방법)
    # 원본 이미지 -> Resize(256) -> CenterCrop(224) -> ToTensor() -> Normalize
    preprocess = transforms.Compose([
        transforms.Resize(256), #리사이즈
        transforms.CenterCrop(224), #중앙 크롭
        transforms.ToTensor(), #텐서 변환
        transforms.Normalize(mean=[0.485, 0.456, 0.406], # R G B 평균
                            std=[0.229, 0.224, 0.225])  # R G B 표준편차 
    ])

    # 이미지 임베딩
    try:
        image = Image.open(image_path).convert('RGB')
        input_tensor = preprocess(image).unsqueeze(0) # 전처리
        
        with torch.no_grad():
            embedding = model(input_tensor).flatten() # 임베딩
        
        return embedding.cpu().numpy().tolist()
    
    except Exception as e:
        print(f"  Error: 임베딩 생성 실패 ({image_path}): {e}")
        return None



# 25개 경로를 돌면서 각 이미지를 [메타데이터 + 임베딩 벡터] 로 구성된 JSON 객체로 변환

img_data_list = []

for img_path in image_paths:
    file_name = os.path.basename(img_path)

    #파일명에서 메타데이터 추출
    meta = metadata(file_name)

    #임베딩 벡터 생성
    embd = embedding(img_path) 

    # JSON 객체 생성
    json_obj = {

        "embedding": embd,
        "metadata": {

            "id": str(meta['id']),
            "era": meta.get('era', 'unknown'),
            "style": meta.get('style', 'unknown'),
            "gender": meta.get('gender', 'unknown'),
            'url': meta.get('url', ''),
        }
    }

    img_data_list.append(json_obj) 

#결과 확인
print(f"\n총 {len(img_data_list)}개 이미지 데이터 생성 완료\n")
print("첫번째 이미지 데이터 예시:")
print(img_data_list[0]["metadata"], "\n임베딩 벡터:", img_data_list[0]["embedding"][:5], "...", img_data_list[0]["embedding"][-5:])
print("임베딩 벡터 크기:", np.array(img_data_list[0]["embedding"]).shape)

'''
# Pickle 파일로 저장
with open("img_data_list.pkl", "wb") as f:
    pickle.dump(img_data_list, f)
print("img_data_list.pkl 저장 완료")

#json 파일로 저장
import json
with open("img_data_list.json", "w", encoding="utf-8") as f:
    json.dump(img_data_list, f, ensure_ascii=False, indent=4)
print("img_data_list.json 저장 완료")
'''
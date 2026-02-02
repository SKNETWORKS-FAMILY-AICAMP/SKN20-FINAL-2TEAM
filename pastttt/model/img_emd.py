from PIL import Image
import torch
import torchvision.transforms as transforms
from torchvision.models import resnet50
import numpy as np
import os
import pickle  
#pip install torch torchvision pillow << 최초 1회

'''
RESNET 모델을 사용해, 이미지 임베딩 벡터 생성
-> VECTOR DB에 넣기
-> 새로운 이미지를 질문으로 입력
-> 25장 중에서, 입력 이미지랑 가장 유사한 이미지를 찾아서 보여줌.

리트리버가 벡터 DB에서 유사한 이미지를 찾았어. 그럼 답변으로 어떻게 보여주지? 특징 벡터를 보여주면 안될텐데. 
>>>  각 이미지에 대한 메타데이터(파일명, 경로 등)도 같이 벡터 DB에 넣어두자. -> preprocessing.py에서 구현
'''

# resnet 모델 로드
model = resnet50(pretrained=True)
model = torch.nn.Sequential(*list(model.children())[:-1])  # 마지막 분류층 제거(특징 추출만 필요하므로)
model.eval()

# 이미지 전처리 파이프라인 
# RESNET 표준 방법 사용 (RESNET 모델을 사용할 때 권장되는 전처리 방법)
# 원본 이미지 -> Resize(256) -> CenterCrop(224) -> ToTensor() -> Normalize
preprocess = transforms.Compose([
    transforms.Resize(256), #리사이즈
    transforms.CenterCrop(224), #중앙 크롭
    transforms.ToTensor(), #텐서 변환
    transforms.Normalize(mean=[0.485, 0.456, 0.406], # R G B 평균
                         std=[0.229, 0.224, 0.225])  # R G B 표준편차 
])

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

print(f"총 발견된 이미지: {len(image_paths)}개\n")


# 이미지 임베딩 생성
embeddings = []
for idx, image_path in enumerate(image_paths, 1):
    try:
        image = Image.open(image_path).convert('RGB')
        input_tensor = preprocess(image).unsqueeze(0) # 전처리
        
        with torch.no_grad():
            embedding = model(input_tensor).flatten() # 임베딩 
        
        embeddings.append(embedding.cpu().numpy())
        print(f"[{idx}/{len(image_paths)}] 임베딩 완료: {os.path.basename(image_path)}")
        
    except Exception as e:
        print(f"error 발생: ({image_path}): {e}")

# 결과
print(f"총 {len(embeddings)}개 이미지 임베딩 완료")
print(f"임베딩 벡터 크기: {embeddings[0].shape}")
print(f"첫번째 이미지 임배당 백터: {embeddings[0][:5]} ... {embeddings[0][-5:]}")

'''
# Pickle 파일로 저장
with open("embeddings.pkl", "wb") as f:
    pickle.dump(embeddings, f)  
print("embeddings.pkl 저장 완료")
'''




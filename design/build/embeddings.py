import json
import requests
import os
from pathlib import Path
from PIL import Image
from io import BytesIO
import torch
import numpy as np
import sys
import clip

'''
각 도면 json파일에서  이미지를 다운받는다. (-> jpg 형태로 "data/images" 폴더에 저장된다.)

다운받은 이미지를 불러와, clip으로 이미지 임베딩 벡터(512차원)를 생성한다. 

{임베딩 벡터/메타데이터} 구조의 json 포맷으로 저장한다. (-> "data/embeddings" 폴더에 저장된다.)
'''
'''
# CLIP 동적 로드 - 최초 1회만
try:
    import clip
except ImportError:
    print("CLIP 패키지를 설치 중...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "git+https://github.com/openai/CLIP.git"])
    import clip
'''


# CLIP 모델 로드 (ViT-B/32)
print("CLIP 모델 로딩 중...")
device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)
print(f"모델 로드 완료 (Device: {device})")

# json 파일이 있는 폴더
JSON_FOLDER = r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM\design\data\json"
# 이미지 저장할 폴더
DOWNLOAD_DIR = r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM\design\data\images_2"
# 벡터DB에 적재할 json(임베딩 벡터 포함 버전) 저장할 폴더
EMBEDDING_OUTPUT = r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM\design\data\embeddings"
# 에러 기록 파일
ERROR_LOG = r"C:\Users\playdata2\Desktop\SKN_AI_20\SKN20-FINAL-2TEAM\design\data\error_log.txt"

# 디렉토리 생성
Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(EMBEDDING_OUTPUT).mkdir(parents=True, exist_ok=True)

#폴더 내 모든 파일 리스트 가져오기
list = os.listdir(JSON_FOLDER) 

#for 문으로 폴더 내 모든 json 파일 처리
for idx, filename in enumerate(list,1):
    if not filename.endswith(".json"):
        continue

    JSON_FILE = os.path.join(JSON_FOLDER, filename)
    print(f"\n{'='*50}")
    print(f"{idx}/{len(list)} 처리 중: {filename}")
    print(f"{'='*50}")


    # JSON 파일 읽기
    print(f"\nJSON 파일 읽기: {JSON_FILE}")
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 이미지 경로 추출
    image_path = data.get('image', {}).get('imagePath')
    image_name = data.get('image', {}).get('imageName', 'image.jpg')
    design_id = data.get('design_id', 'unknown')

    # 이미 처리된 파일이면 skip (이어받기)
    image_number_pre = data.get('image', {}).get('number', '1')
    output_file_pre = os.path.join(EMBEDDING_OUTPUT, f"{design_id}-{image_number_pre}_embedding.json")
    if os.path.exists(output_file_pre):
        print(f"SKIP: 이미 처리됨 → {output_file_pre}")
        continue

    if not image_path:
        msg = f"[{filename}] imagePath를 찾을 수 없습니다."
        print(f"ERROR: {msg}")
        with open(ERROR_LOG, 'a', encoding='utf-8') as ef:
            ef.write(msg + "\n")
        continue

    print(f"이미지 경로: {image_path}")
    print(f"이미지 이름: {image_name}")
    print(f"디자인 ID: {design_id}")

    # 이미지 다운로드
    print("\n이미지 다운로드 중...")
    try:
        # get 요청으로 이미지 다운로드
        response = requests.get(image_path, timeout=30) 
        response.raise_for_status()
        
        # 이미지 저장
        image_file_path = os.path.join(DOWNLOAD_DIR, f"{design_id}_{image_name}")
        with open(image_file_path, 'wb') as f:
            f.write(response.content)
        
        print(f"✓ 이미지 저장 완료: {image_file_path}")
        
        # 이미지 로드
        image = Image.open(image_file_path).convert('RGB')
        print(f"✓ 이미지 크기: {image.size}")
        
        # CLIP 전처리 및 임베딩
        image_tensor = preprocess(image).unsqueeze(0).to(device)
        
        with torch.no_grad():
            image_embedding = model.encode_image(image_tensor)
        
        # 임베딩을 CPU로 이동 후 numpy로 변환
        embedding_array = image_embedding.cpu().numpy()
        
        print(f"✓ 임베딩 완료")
        print(f"  - 임베딩 크기: {embedding_array.shape}")
        print(f"  - 임베딩 차원: {embedding_array.shape[1]}")
        print(f"  - 첫 10개 값: {embedding_array[0, :10]}")
        
        # 메타데이터 추출
        application_number = data.get('applicationNumber', '')
        registration_number = data.get('registrationNumber', '')
        status = data.get('status', {})
        meta = data.get('meta', {})
        image = data.get('image', {})
        creative = data.get('creative', {})
        
        # 결과 저장 (JSON 형식)
        image_number = image.get('number', '1')
        id_field = f"{design_id}-IMG-{image_number}"
        
        output_file = os.path.join(EMBEDDING_OUTPUT, f"{design_id}-{image_number}_embedding.json")
        result = {
            "id": id_field,
            "embedding": embedding_array.tolist()[0],  # 첫 번째 배치 항목
            "metadata": {
                "design_id": design_id, #디자인id
                "applicationNumber": application_number, #출원번호
                "registrationNumber": registration_number, #등록번호
                "status": status, #상태
                "articleName": meta.get('articleName', ''), #상품명
                "LCCode": meta.get('LCCode', ''), #LCCode
                "image_id": image.get('image_id', ''), #이미지id
                "imagePath": image_path, #이미지경로
                "imageNumber": image_number, #도면번호
                "designSummary": creative.get('designSummary', '') #디자인 요약
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"\n✓ 임베딩 저장 완료: {output_file}")
        
        
    except requests.exceptions.RequestException as e:
        msg = f"[{filename}] 이미지 다운로드 실패 - {e}"
        print(f"ERROR: {msg}")
        with open(ERROR_LOG, 'a', encoding='utf-8') as ef:
            ef.write(msg + "\n")
        continue
    except Exception as e:
        msg = f"[{filename}] {type(e).__name__}: {e}"
        print(f"ERROR: {msg}")
        with open(ERROR_LOG, 'a', encoding='utf-8') as ef:
            ef.write(msg + "\n")
        continue

    print("작업 완료!")
    print(f"다운로드된 이미지: {DOWNLOAD_DIR}")
    print(f"임베딩 저장 위치: {EMBEDDING_OUTPUT}")
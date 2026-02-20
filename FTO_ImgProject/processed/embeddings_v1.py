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
from datetime import datetime

'''
각 도면 json파일에서  이미지를 다운받는다. (-> jpg 형태로 "./images" 폴더에 저장된다.)

다운받은 이미지를 불러와, clip으로 이미지 임베딩 벡터(512차원)를 생성한다. 

{임베딩 벡터/메타데이터} 구조의 json 포맷으로 저장한다. (-> "./embeddings" 폴더에 저장된다.)
'''

# CLIP 모델 로드 (ViT-B/32)
print("CLIP 모델 로딩 중...")
device = "mps" if torch.backends.mps.is_available() else "cpu" if not torch.cuda.is_available() else "cuda"
model, preprocess = clip.load("ViT-B/32", device=device)
print(f"모델 로드 완료 (Device: {device})")

# json 파일이 있는 폴더
JSON_FOLDER = r"/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/평가데이터/json_reject"
# 이미지 저장할 폴더
DOWNLOAD_DIR = r"/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/평가데이터/images_reject"
# 벡터DB에 적재할 json(임베딩 벡터 포함 버전) 저장할 폴더
EMBEDDING_OUTPUT = r"/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/평가데이터/embeddings_reject"
# 에러 로그 파일
ERROR_LOG = r"/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/평가데이터/reject_error/embeddingError.txt"

# 디렉토리 생성
Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(EMBEDDING_OUTPUT).mkdir(parents=True, exist_ok=True)

# 에러 로그 초기화
with open(ERROR_LOG, 'w', encoding='utf-8') as f:
    f.write(f"=== 이미지 처리 에러 로그 ===\n")
    f.write(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

# 통계 변수
total_files = 0
success_count = 0
error_count = 0

#폴더 내 모든 파일 리스트 가져오기
list = os.listdir(JSON_FOLDER) 
json_files = [f for f in list if f.endswith(".json")]
total_files = len(json_files)

#for 문으로 폴더 내 모든 json 파일 처리
for idx, filename in enumerate(json_files, 1):
    JSON_FILE = os.path.join(JSON_FOLDER, filename)
    print(f"\n{'='*50}")
    print(f"{idx}/{total_files} 처리 중: {filename}")
    print(f"{'='*50}")

    try:
        # JSON 파일 읽기
        print(f"\nJSON 파일 읽기: {JSON_FILE}")
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 이미지 경로 추출
        image_path = data.get('image', {}).get('imagePath')
        image_name = data.get('image', {}).get('imageName', 'image.jpg')
        design_id = data.get('design_id', 'unknown')

        if not image_path:
            error_msg = f"ERROR: {filename} - imagePath를 찾을 수 없습니다."
            print(error_msg)
            with open(ERROR_LOG, 'a', encoding='utf-8') as f:
                f.write(f"{error_msg}\n")
            error_count += 1
            continue

        print(f"이미지 경로: {image_path}")
        print(f"이미지 이름: {image_name}")
        print(f"디자인 ID: {design_id}")

        # 이미지 다운로드
        print("\n이미지 다운로드 중...")
        
        # get 요청으로 이미지 다운로드
        response = requests.get(image_path, timeout=30) 
        response.raise_for_status()
        
        # 이미지 저장
        image_file_path = os.path.join(DOWNLOAD_DIR, f"{design_id}_{image_name}")
        with open(image_file_path, 'wb') as f:
            f.write(response.content)
        
        print(f"✓ 이미지 저장 완료: {image_file_path}")
        
        # 이미지 로드 및 검증
        try:
            image = Image.open(image_file_path).convert('RGB')
            print(f"✓ 이미지 크기: {image.size}")
        except Exception as img_error:
            error_msg = f"ERROR: {filename} - 이미지 파일 손상 또는 형식 오류: {image_file_path}\n  상세: {str(img_error)}"
            print(error_msg)
            with open(ERROR_LOG, 'a', encoding='utf-8') as f:
                f.write(f"{error_msg}\n\n")
            error_count += 1
            continue
        
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
        success_count += 1
        
    except requests.exceptions.RequestException as e:
        error_msg = f"ERROR: {filename} - 이미지 다운로드 실패\n  URL: {image_path}\n  상세: {str(e)}"
        print(error_msg)
        with open(ERROR_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{error_msg}\n\n")
        error_count += 1
        continue
        
    except Exception as e:
        error_msg = f"ERROR: {filename} - 예상치 못한 오류\n  상세: {str(e)}"
        print(error_msg)
        with open(ERROR_LOG, 'a', encoding='utf-8') as f:
            f.write(f"{error_msg}\n\n")
        error_count += 1
        continue

# 최종 통계 출력
print(f"\n{'='*50}")
print("전체 작업 완료!")
print(f"{'='*50}")
print(f"총 파일 수: {total_files}")
print(f"성공: {success_count}")
print(f"실패: {error_count}")
print(f"\n다운로드된 이미지: {DOWNLOAD_DIR}")
print(f"임베딩 저장 위치: {EMBEDDING_OUTPUT}")
print(f"에러 로그: {ERROR_LOG}")

# 에러 로그에 최종 통계 추가
with open(ERROR_LOG, 'a', encoding='utf-8') as f:
    f.write(f"\n{'='*50}\n")
    f.write(f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"총 파일 수: {total_files}\n")
    f.write(f"성공: {success_count}\n")
    f.write(f"실패: {error_count}\n")
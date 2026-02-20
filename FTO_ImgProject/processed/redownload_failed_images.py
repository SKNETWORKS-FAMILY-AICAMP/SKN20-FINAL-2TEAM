import os
import json
import requests
from pathlib import Path
from datetime import datetime
from PIL import Image
import torch
import clip

# 경로 설정
ERROR_LOG = r"/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/error_log.txt"
JSON_FOLDER = r"/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/json"
DOWNLOAD_DIR = r"/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/images"
EMBEDDING_OUTPUT = r"/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/embeddings"

Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(EMBEDDING_OUTPUT).mkdir(parents=True, exist_ok=True)

# CLIP 모델 로드
print("CLIP 모델 로딩 중...")
device = "cuda" if torch.cuda.is_available() else "cpu"
model, preprocess = clip.load("ViT-B/32", device=device)
print(f"모델 로드 완료 (Device: {device})")

# 실패 로그에서 json 파일명 추출
def extract_failed_jsons(error_log_path):
    failed_jsons = []
    with open(error_log_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.endswith('.json'):
                # ERROR: 3020210060457-2.json - ... 형태도 처리
                if 'ERROR:' in line:
                    parts = line.split()
                    for part in parts:
                        if part.endswith('.json'):
                            failed_jsons.append(part)
                            break
                else:
                    failed_jsons.append(line)
    return list(set(failed_jsons))  # 중복 제거

failed_jsons = extract_failed_jsons(ERROR_LOG)
total_files = len(failed_jsons)
success_count = 0
error_count = 0

print(f"총 {total_files}개 실패 json 재시도")

for idx, filename in enumerate(failed_jsons, 1):
    json_path = os.path.join(JSON_FOLDER, filename)
    if not os.path.exists(json_path):
        print(f"⚠️  SKIP: {json_path} 파일 없음")
        error_count += 1
        continue
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        image_path = data.get('image', {}).get('imagePath')
        image_name = data.get('image', {}).get('imageName', 'image.jpg')
        design_id = data.get('design_id', 'unknown')
        if not image_path:
            print(f"⚠️  SKIP: {filename} - imagePath 없음")
            error_count += 1
            continue
        print(f"{idx}/{total_files} 다운로드: {filename} -> {image_path}")
        response = requests.get(image_path, timeout=30)
        response.raise_for_status()
        image_file_path = os.path.join(DOWNLOAD_DIR, f"{design_id}_{image_name}")
        with open(image_file_path, 'wb') as f:
            f.write(response.content)
        print(f"✓ 저장 완료: {image_file_path}")
        # 임베딩 생성
        try:
            image = Image.open(image_file_path).convert('RGB')
            image_tensor = preprocess(image).unsqueeze(0).to(device)
            with torch.no_grad():
                image_embedding = model.encode_image(image_tensor)
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
            image_info = data.get('image', {})
            creative = data.get('creative', {})
            image_number = image_info.get('number', '1')
            id_field = f"{design_id}-IMG-{image_number}"
            output_file = os.path.join(EMBEDDING_OUTPUT, f"{design_id}-{image_number}_embedding.json")
            result = {
                "id": id_field,
                "embedding": embedding_array.tolist()[0],
                "metadata": {
                    "design_id": design_id,
                    "applicationNumber": application_number,
                    "registrationNumber": registration_number,
                    "status": status,
                    "articleName": meta.get('articleName', ''),
                    "LCCode": meta.get('LCCode', ''),
                    "image_id": image_info.get('image_id', ''),
                    "imagePath": image_path,
                    "imageNumber": image_number,
                    "designSummary": creative.get('designSummary', '')
                }
            }
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"\n✓ 임베딩 저장 완료: {output_file}")
            success_count += 1
        except Exception as img_error:
            print(f"⚠️  임베딩 실패: {filename} - {img_error}")
            error_count += 1
            continue
    except requests.exceptions.RequestException as e:
        print(f"⚠️  이미지 다운로드 실패: {filename} - {e}")
        error_count += 1
        continue
    except Exception as e:
        print(f"⚠️  예상치 못한 오류: {filename} - {e}")
        error_count += 1
        continue

print(f"\n{'='*50}")
print("전체 작업 완료!")
print(f"{'='*50}")
print(f"총 파일 수: {total_files}")
print(f"성공: {success_count}")
print(f"실패: {error_count}")
print(f"\n다운로드된 이미지: {DOWNLOAD_DIR}")
print(f"임베딩 저장 위치: {EMBEDDING_OUTPUT}")
print(f"에러 로그: {ERROR_LOG}")

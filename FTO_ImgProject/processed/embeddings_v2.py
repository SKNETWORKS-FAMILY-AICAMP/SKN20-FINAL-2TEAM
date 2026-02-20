import json
import requests
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
from PIL import Image
from io import BytesIO
import torch
import numpy as np
import torch.nn.functional as F
import cv2
import clip
from datetime import datetime

'''
각 도면 json파일에서 이미지를 다운받는다. (-> jpg 형태로 "images_v2" 폴더에 저장)

다운받은 이미지를 불러와:
1) 사진/스케치 자동 감지
2) 사진이면 스케치로 변환 (Canny Edge Detection)
3) 이미 스케치 도면인 경우 그대로 사용

최종적으로 clip으로 이미지 임베딩 벡터(512차원)를 생성하고
{임베딩 벡터/메타데이터} 구조의 json 포맷으로 저장 (-> "embeddings_v2" 폴더)
'''

# ============================================
# 스케치 변환 함수들
# ============================================

def detect_if_photo(image):
    """
    이미지가 사진인지 스케치인지 자동 판별
    
    판별 기준:
    - 흰색 비율: 스케치 도면은 배경이 대부분 흰색 (>85%)
    - 평균 밝기: 스케치 도면은 매우 밝음 (>250)
    - 사진은 흰색 비율 낮고 (<95%), 밝기도 상대적으로 낮음
    """
    img_array = np.array(image.convert('L'))  # 그레이스케일
    
    # 흰색 픽셀 비율 계산 (240 이상을 흰색으로 간주)
    white_ratio = np.sum(img_array > 260) / img_array.size
    
    # 평균 밝기 계산
    mean_brightness = np.mean(img_array)
    
    # 판별 기준
    is_sketch = (white_ratio > 0.95 and mean_brightness > 250)
    is_photo = not is_sketch
    
    print(f"  - 흰색 비율: {white_ratio:.3f} ({white_ratio*100:.1f}%)")
    print(f"  - 평균 밝기: {mean_brightness:.1f}")
    print(f"  - 판별 결과: {'사진' if is_photo else '스케치'}")
    
    return is_photo


def convert_to_sketch(image):
    """
    이미지를 스케치로 변환 (Canny Edge Detection 기반)
    
    Args:
        image: PIL Image (RGB)
    
    Returns:
        sketch: PIL Image (RGB, 흰 배경에 검은 선)
    """
    # PIL → OpenCV
    img_array = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2GRAY)
    
    # 노이즈 제거
    blurred = cv2.GaussianBlur(img_array, (5, 5), 1.0)
    
    # Canny 엣지 검출
    edges = cv2.Canny(blurred, 30, 120)
    edges = cv2.dilate(edges, np.ones((2,2), np.uint8), iterations=1)
    
    # 반전 (검은 배경 → 흰 배경)
    sketch = 255 - edges
    
    # RGB로 변환
    sketch_rgb = cv2.cvtColor(sketch, cv2.COLOR_GRAY2RGB)
    
    return Image.fromarray(sketch_rgb)


def preprocess_with_sketch(image, use_sketch=True):
    """
    사진/스케치 자동 감지 + 스케치 변환
    
    Args:
        image: PIL Image 객체
        use_sketch: True면 사진을 스케치로 변환
    
    Returns:
        processed: PIL Image (전처리된 이미지)
    """
    # 사진인지 스케치인지 자동 감지
    is_photo = detect_if_photo(image)
    
    # 사진이면 스케치로 변환
    if is_photo and use_sketch:
        print("  → 사진 감지 → 스케치 변환 중...")
        processed = convert_to_sketch(image)
    else:
        print("  → 스케치 이미지로 인식 → 원본 그대로 유지")
        processed = image
    
    return processed


# ============================================
# 메인 처리 로직
# ============================================

# CLIP 모델 로드 (ViT-B/32)
print("CLIP 모델 로딩 중...")
device = "mps" if torch.backends.mps.is_available() else "cpu" if not torch.cuda.is_available() else "cuda"
model, preprocess = clip.load("ViT-B/32", device=device)
print(f"모델 로드 완료 (Device: {device})")

# 경로 설정
JSON_FOLDER = str(PROJECT_ROOT / "data/json")
DOWNLOAD_DIR = str(PROJECT_ROOT / "data/sketch/images_v2")
EMBEDDING_OUTPUT = str(PROJECT_ROOT / "data/sketch/embeddings_v2")
ERROR_LOG = str(PROJECT_ROOT / "data/error_Flow/5.embedding_failed_v2.txt")

# 디렉토리 생성
Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)
Path(EMBEDDING_OUTPUT).mkdir(parents=True, exist_ok=True)

# 에러 로그 초기화
with open(ERROR_LOG, 'w', encoding='utf-8') as f:
    f.write(f"=== 이미지 처리 에러 로그 (스케치 변환 포함) ===\n")
    f.write(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

# 통계 변수
total_files = 0
success_count = 0
error_count = 0
photo_converted_count = 0  # 사진→스케치 변환 횟수
sketch_count = 0  # 원본 스케치 도면 횟수

# JSON 파일 리스트 가져오기
list_files = os.listdir(JSON_FOLDER)
json_files = [f for f in list_files if f.endswith(".json")]
total_files = len(json_files)

print(f"\n총 {total_files}개의 JSON 파일을 처리합니다.\n")

# 모든 JSON 파일 처리
for idx, filename in enumerate(json_files, 1):
    JSON_FILE = os.path.join(JSON_FOLDER, filename)
    print(f"\n{'='*60}")
    print(f"[{idx}/{total_files}] 처리 중: {filename}")
    print(f"{'='*60}")

    try:
        # JSON 파일 읽기
        print(f"JSON 파일 읽기...")
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

        print(f"디자인 ID: {design_id}")
        print(f"이미지 경로: {image_path}")

        # 이미지 다운로드
        print("\n[1단계] 이미지 다운로드 중...")
        response = requests.get(image_path, timeout=30)
        response.raise_for_status()
        
        # 메모리에서 이미지 로드
        original_image = Image.open(BytesIO(response.content)).convert('RGB')
        print(f"✓ 원본 이미지 크기: {original_image.size}")
        
        # [2단계] 스케치 변환 (자동 감지)
        print("\n[2단계] 사진/스케치 자동 감지 및 변환...")
        is_photo_before = detect_if_photo(original_image)
        processed_image = preprocess_with_sketch(original_image, use_sketch=True)
        
        if is_photo_before:
            photo_converted_count += 1
        else:
            sketch_count += 1
        
        # 전처리된 이미지 저장
        image_file_path = os.path.join(DOWNLOAD_DIR, f"{design_id}_{image_name}")
        processed_image.save(image_file_path)
        print(f"✓ 전처리 이미지 저장: {image_file_path}")
        
        # [3단계] CLIP 임베딩
        print("\n[3단계] CLIP 임베딩 생성 중...")
        image_tensor = preprocess(processed_image).unsqueeze(0).to(device)
        
        with torch.no_grad():
            image_embedding = model.encode_image(image_tensor)
            image_embedding = F.normalize(image_embedding, dim=-1)  # ← 이 줄 추가 (F.normalize를 임베딩 저장 시 적용)
        
        # 임베딩을 CPU로 이동 후 numpy로 변환
        embedding_array = image_embedding.cpu().numpy()
        
        print(f"✓ 임베딩 완료")
        print(f"  - 임베딩 차원: {embedding_array.shape[1]}")
        print(f"  - 임베딩 크기: {embedding_array.shape}")
        
        # [4단계] 메타데이터 추출 및 저장
        print("\n[4단계] JSON 저장 중...")
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
            "embedding": embedding_array.tolist()[0],  # 첫 번째 배치 항목
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
                "designSummary": creative.get('designSummary', ''),
                "is_converted_to_sketch": is_photo_before  # 스케치 변환 여부 기록
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"✓ 임베딩 저장 완료: {output_file}")
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

# ============================================
# 최종 통계 출력
# ============================================
print(f"\n{'='*60}")
print("전체 작업 완료!")
print(f"{'='*60}")
print(f"총 파일 수: {total_files}")
print(f"성공: {success_count}")
print(f"실패: {error_count}")
print(f"\n[스케치 변환 통계]")
print(f"사진→스케치 변환: {photo_converted_count}개")
print(f"원본 스케치 유지: {sketch_count}개")
print(f"\n[출력 경로]")
print(f"다운로드된 이미지: {DOWNLOAD_DIR}")
print(f"임베딩 저장 위치: {EMBEDDING_OUTPUT}")
print(f"에러 로그: {ERROR_LOG}")

# 에러 로그에 최종 통계 추가
with open(ERROR_LOG, 'a', encoding='utf-8') as f:
    f.write(f"\n{'='*60}\n")
    f.write(f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    f.write(f"총 파일 수: {total_files}\n")
    f.write(f"성공: {success_count}\n")
    f.write(f"실패: {error_count}\n")
    f.write(f"사진→스케치 변환: {photo_converted_count}개\n")
    f.write(f"원본 스케치 유지: {sketch_count}개\n")
    
# ```

# ## 주요 변경 사항

# ### 1. **통합된 워크플로우**
# - JSON 읽기 → 이미지 다운로드 → 스케치 변환 → CLIP 임베딩 → JSON 저장
# - 한 루프에서 모든 작업 처리

# ### 2. **스케치 변환 자동화**
# - `detect_if_photo()`: 흰색 비율(85%), 평균 밝기(230) 기준으로 사진/스케치 자동 판별
# - `convert_to_sketch()`: Canny Edge Detection으로 사진→스케치 변환
# - 이미 스케치인 경우 원본 유지

# ### 3. **메모리 효율**
# - 다운로드한 이미지를 메모리에서 직접 처리 (`BytesIO` 사용)
# - 전처리 완료 후 파일로 저장

# ### 4. **통계 추적**
# - 사진→스케치 변환 횟수
# - 원본 스케치 유지 횟수
# - 메타데이터에 `is_converted_to_sketch` 필드 추가

# ### 5. **폴더 구조**
# ```
# images_v2/       # 전처리된 이미지 (스케치 변환 포함)
# embeddings_v2/   # CLIP 임베딩 JSON
# error_log_v2.txt # 에러 로그
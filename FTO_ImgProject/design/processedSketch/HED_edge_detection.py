#!/usr/bin/env python3
"""
Holistically-Nested Edge Detection (HED)
딥러닝 기반 엣지 검출 (가장 정확)

장점:
- CNN 기반으로 가장 정확한 엣지 검출
- 객체 경계를 매우 정확하게 찾음
- 노이즈에 매우 강함
- 얇고 연결성 좋은 엣지

단점:
- 사전 학습된 모델 필요 (deploy.prototxt + .caffemodel)
- 처리 속도 느림 (GPU 권장)
- 모델 크기 큼 (~56MB)

모델 다운로드:
https://github.com/s9xie/hed
파일: deploy.prototxt, hed_pretrained_bsds.caffemodel
"""

import cv2
import numpy as np
import urllib.request
import os
from pathlib import Path
from typing import Tuple, Optional


def download_hed_model(
    prototxt_path: str = "./deploy.prototxt",
    model_path: str = "./hed_pretrained_bsds.caffemodel"
) -> Tuple[str, str]:
    """
    HED 모델 자동 다운로드
    
    Returns:
        (prototxt_path, model_path)
    """
    # Prototxt 다운로드
    if not os.path.exists(prototxt_path):
        print("📥 deploy.prototxt 다운로드 중...")
        url_prototxt = "https://raw.githubusercontent.com/s9xie/hed/master/examples/hed/deploy.prototxt"
        try:
            urllib.request.urlretrieve(url_prototxt, prototxt_path)
            print(f"✅ Prototxt 다운로드 완료: {prototxt_path}")
        except Exception as e:
            raise RuntimeError(f"❌ Prototxt 다운로드 실패: {e}")
    
    # Caffemodel 다운로드 (크기: ~56MB)
    if not os.path.exists(model_path):
        print("📥 hed_pretrained_bsds.caffemodel 다운로드 중... (크기: ~56MB)")
        print("   ⚠️  다운로드에 시간이 걸릴 수 있습니다.")
        
        # Google Drive 링크 (공식 모델)
        # 직접 다운로드가 어려우므로 사용자에게 안내
        print("\n⚠️  모델 파일을 수동으로 다운로드해야 합니다.")
        print("1. https://vcl.ucsd.edu/hed/hed_pretrained_bsds.caffemodel 접속")
        print(f"2. 파일을 다운로드하여 {model_path}에 저장")
        print("\n또는 다음 명령어 실행:")
        print(f"wget https://vcl.ucsd.edu/hed/hed_pretrained_bsds.caffemodel -O {model_path}")
        raise FileNotFoundError(f"모델 파일이 필요합니다: {model_path}")
    
    return prototxt_path, model_path


class CropLayer(object):
    """
    HED 모델의 Crop 레이어 구현
    OpenCV DNN에서 Caffe의 Crop 레이어를 지원하지 않으므로 직접 구현
    """
    def __init__(self, params, blobs):
        self.xstart = 0
        self.ystart = 0
    
    def getMemoryShapes(self, inputs):
        # 입력/출력 shape 반환
        inputShape, targetShape = inputs[0], inputs[1]
        batchSize, numChannels = inputShape[0], inputShape[1]
        height, width = targetShape[2], targetShape[3]
        
        self.ystart = (inputShape[2] - targetShape[2]) // 2
        self.xstart = (inputShape[3] - targetShape[3]) // 2
        
        return [[batchSize, numChannels, height, width]]
    
    def forward(self, inputs):
        # Crop 연산 수행
        return [inputs[0][:, :, 
                self.ystart:self.ystart + inputs[1].shape[2],
                self.xstart:self.xstart + inputs[1].shape[3]]]


def load_hed_model(
    prototxt_path: str = "./deploy.prototxt",
    model_path: str = "./hed_pretrained_bsds.caffemodel",
    auto_download: bool = False
) -> cv2.dnn_Net:
    """
    HED 모델 로드
    
    Args:
        prototxt_path: 모델 구조 파일
        model_path: 학습된 가중치 파일
        auto_download: 자동 다운로드 시도 (prototxt만)
    
    Returns:
        OpenCV DNN 네트워크
    """
    # 파일 존재 확인
    if not os.path.exists(prototxt_path) or not os.path.exists(model_path):
        if auto_download:
            prototxt_path, model_path = download_hed_model(prototxt_path, model_path)
        else:
            raise FileNotFoundError(
                f"모델 파일이 없습니다:\n"
                f"  - {prototxt_path}\n"
                f"  - {model_path}\n"
                f"download_hed_model() 함수를 실행하거나 수동으로 다운로드하세요."
            )
    
    # Caffe 모델 로드
    print("📦 HED 모델 로드 중...")
    net = cv2.dnn.readNetFromCaffe(prototxt_path, model_path)
    
    # Crop 레이어 등록 (OpenCV DNN에서 지원하지 않으므로)
    cv2.dnn_registerLayer('Crop', CropLayer)
    
    print("✅ HED 모델 로드 완료")
    return net


def hed_edge_detection(
    img: np.ndarray,
    net: Optional[cv2.dnn_Net] = None,
    prototxt_path: str = "./deploy.prototxt",
    model_path: str = "./hed_pretrained_bsds.caffemodel",
    auto_download: bool = False
) -> np.ndarray:
    """
    HED 엣지 검출
    
    Args:
        img: 입력 이미지 (BGR)
        net: 사전 로드된 네트워크 (None이면 자동 로드)
        prototxt_path: 모델 구조 파일
        model_path: 가중치 파일
        auto_download: 자동 다운로드 시도
    
    Returns:
        엣지 맵 (0.0~1.0, float32)
    """
    # 모델 로드 (필요시)
    if net is None:
        net = load_hed_model(prototxt_path, model_path, auto_download)
    
    # 입력 이미지 전처리
    H, W = img.shape[:2]
    
    # HED는 RGB 순서 사용
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # Mean subtraction (ImageNet 평균)
    mean = np.array([104.00698793, 116.66876762, 122.67891434])
    
    # Blob 생성 (배치 크기 1, 크기 유지, mean subtraction, RGB)
    blob = cv2.dnn.blobFromImage(
        img_rgb,
        scalefactor=1.0,
        size=(W, H),  # 원본 크기 유지
        mean=mean,
        swapRB=False,  # 이미 RGB로 변환했으므로 False
        crop=False
    )
    
    # 네트워크 입력 설정
    net.setInput(blob)
    
    # Forward pass
    print("🔄 HED 추론 중... (시간이 걸릴 수 있습니다)")
    hed = net.forward()
    
    # 출력 후처리
    # hed shape: (1, 1, H, W)
    hed = hed[0, 0]  # (H, W)
    
    # Resize (원본 크기로)
    hed = cv2.resize(hed, (W, H))
    
    # 0~1 범위로 정규화 (이미 sigmoid 통과했으므로 0~1 사이)
    hed = np.clip(hed, 0.0, 1.0)
    
    return hed


def hed_multi_scale(
    img: np.ndarray,
    net: Optional[cv2.dnn_Net] = None,
    scales: list = [0.5, 1.0, 1.5],
    **kwargs
) -> np.ndarray:
    """
    Multi-scale HED 엣지 검출
    
    Args:
        img: 입력 이미지
        net: HED 네트워크
        scales: 스케일 리스트 (1.0 = 원본 크기)
        **kwargs: hed_edge_detection의 다른 파라미터
    
    Returns:
        Multi-scale 결합 엣지 맵
    """
    H, W = img.shape[:2]
    edge_maps = []
    
    for scale in scales:
        # 이미지 리사이즈
        new_h, new_w = int(H * scale), int(W * scale)
        resized = cv2.resize(img, (new_w, new_h))
        
        # HED 엣지 검출
        edges = hed_edge_detection(resized, net=net, **kwargs)
        
        # 원본 크기로 리사이즈
        edges = cv2.resize(edges, (W, H))
        
        edge_maps.append(edges)
    
    # 평균 결합
    combined = np.mean(edge_maps, axis=0)
    
    return combined


def hed_to_binary(
    edges: np.ndarray,
    threshold: float = 0.3,
    max_val: int = 255
) -> np.ndarray:
    """
    HED 엣지 맵을 이진 이미지로 변환
    
    Args:
        edges: HED 엣지 맵 (0.0~1.0)
        threshold: 이진화 임계값 (0.0~1.0)
        max_val: 최댓값 (255)
    
    Returns:
        이진 이미지 (0 or max_val)
    """
    binary = (edges > threshold).astype(np.uint8) * max_val
    return binary


def hed_adaptive_threshold(
    edges: np.ndarray,
    percentile: int = 80,
    max_val: int = 255
) -> np.ndarray:
    """
    Adaptive threshold를 사용한 이진화
    
    Args:
        edges: HED 엣지 맵
        percentile: 백분위수 (0~100)
        max_val: 최댓값
    
    Returns:
        이진 이미지
    """
    # 0이 아닌 엣지값들의 백분위수 계산
    non_zero_edges = edges[edges > 0]
    
    if len(non_zero_edges) > 0:
        threshold = float(np.percentile(non_zero_edges, percentile))
    else:
        threshold = 0.3
    
    binary = (edges > threshold).astype(np.uint8) * max_val
    return binary


def photo_to_sketch_hed(
    img: np.ndarray,
    target_thickness: float = 3.0,
    prototxt_path: str = "./deploy.prototxt",
    model_path: str = "./hed_pretrained_bsds.caffemodel",
    threshold: float = 0.3,
    multi_scale: bool = False,
    scales: list = [0.8, 1.0, 1.2]
) -> np.ndarray:
    """
    HED를 사용한 사진→스케치 변환
    (기존 photo_to_sketch 함수 대체)
    
    Args:
        img: 입력 이미지 (BGR)
        target_thickness: 목표 선 굵기
        prototxt_path: HED 모델 구조
        model_path: HED 가중치
        threshold: 엣지 임계값 (0.2~0.4 추천)
        multi_scale: Multi-scale 사용 여부
        scales: Multi-scale 스케일 리스트
    
    Returns:
        스케치 이미지 (배경=255, 선=0)
    """
    # 1. HED 모델 로드
    net = load_hed_model(prototxt_path, model_path, auto_download=False)
    
    # 2. HED 엣지 검출
    if multi_scale:
        edges = hed_multi_scale(img, net=net, scales=scales)
    else:
        edges = hed_edge_detection(img, net=net)
    
    # 3. 이진화
    binary = hed_to_binary(edges, threshold=threshold)
    
    # 4. Morphological operations
    # HED는 이미 연결성이 좋으므로 최소한의 후처리만
    kernel_open = np.ones((2,2), np.uint8)
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open)
    
    # 5. 선 굵기 조정
    current_thickness = estimate_line_thickness(cleaned)
    
    if current_thickness > 0 and current_thickness < target_thickness:
        ratio = target_thickness / current_thickness
        kernel_size = max(3, min(5, int(ratio * 1.5) | 1))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        edges_final = cv2.dilate(cleaned, kernel, iterations=1)
    else:
        edges_final = cleaned
    
    # 6. 반전 및 이진화 (배경=255, 선=0)
    sketch_final = 255 - edges_final
    sketch_final = np.where(sketch_final > 127, 255, 0).astype(np.uint8)
    
    return sketch_final


def estimate_line_thickness(edges: np.ndarray, percentile: int = 75) -> float:
    """선 굵기 추정 (기존 코드와 동일)"""
    if np.sum(edges) == 0:
        return 0.0
    
    dist_transform = cv2.distanceTransform(edges, cv2.DIST_L2, 5)
    edge_distances = dist_transform[edges > 0]
    
    if len(edge_distances) == 0:
        return 0.0
    
    thickness = float(np.percentile(edge_distances, percentile) * 2)
    return thickness


# =========================
# 간단한 사용법 (모델 없이 안내만)
# =========================

def simple_hed_usage_guide():
    """
    HED 사용 안내
    """
    print("="*80)
    print("🎨 HED (Holistically-Nested Edge Detection) 사용 가이드")
    print("="*80)
    
    print("\n1. 모델 다운로드:")
    print("   - deploy.prototxt:")
    print("     https://raw.githubusercontent.com/s9xie/hed/master/examples/hed/deploy.prototxt")
    print("   - hed_pretrained_bsds.caffemodel (~56MB):")
    print("     https://vcl.ucsd.edu/hed/hed_pretrained_bsds.caffemodel")
    
    print("\n2. 설치 (필요시):")
    print("   pip install opencv-python --break-system-packages")
    
    print("\n3. 기본 사용법:")
    print("""
import cv2
from hed_edge_detection import load_hed_model, hed_edge_detection, hed_to_binary

# 모델 로드
net = load_hed_model("./deploy.prototxt", "./hed_pretrained_bsds.caffemodel")

# 이미지 로드
img = cv2.imread("image.jpg")

# HED 엣지 검출
edges = hed_edge_detection(img, net=net)

# 이진화
binary = hed_to_binary(edges, threshold=0.3)

# 저장
cv2.imwrite("edges.png", (edges * 255).astype('uint8'))
cv2.imwrite("binary.png", binary)
""")
    
    print("\n4. 파라미터 튜닝:")
    print("   - threshold: 0.2~0.4 (낮을수록 많은 엣지)")
    print("   - multi_scale: True (품질 향상, 속도 감소)")
    
    print("="*80)


# =========================
# 테스트 코드
# =========================

if __name__ == "__main__":
    import matplotlib.pyplot as plt
    
    # 모델 파일 확인
    prototxt_path = "./deploy.prototxt"
    model_path = "./hed_pretrained_bsds.caffemodel"
    
    if not os.path.exists(prototxt_path) or not os.path.exists(model_path):
        print("⚠️  HED 모델 파일이 없습니다.")
        simple_hed_usage_guide()
        
        # Prototxt 자동 다운로드 시도
        try:
            download_hed_model(prototxt_path, model_path)
        except:
            print("\n❌ 모델을 자동으로 다운로드할 수 없습니다.")
            print("위 가이드를 참고하여 수동으로 다운로드하세요.")
            exit(1)
    
    # 테스트 이미지 로드
    img_path = "/mnt/user-data/uploads/3020040018820-reject-0_000.JPG"
    img = cv2.imread(img_path)
    
    if img is None:
        print("이미지를 찾을 수 없습니다.")
        exit(1)
    
    print("🔄 HED 엣지 검출 시작...")
    
    # 모델 로드
    net = load_hed_model(prototxt_path, model_path)
    
    # 1. 기본 HED
    print("  1. 기본 HED...")
    edges_basic = hed_edge_detection(img, net=net)
    
    # 2. Multi-scale HED
    print("  2. Multi-scale HED...")
    edges_multi = hed_multi_scale(img, net=net, scales=[0.8, 1.0, 1.2])
    
    # 3. 여러 threshold 테스트
    print("  3. Threshold 테스트...")
    results = {}
    
    for thresh in [0.2, 0.3, 0.4, 0.5]:
        results[f'thresh_{thresh}'] = hed_to_binary(edges_basic, threshold=thresh)
    
    # 4. Adaptive threshold
    print("  4. Adaptive threshold...")
    results['adaptive'] = hed_adaptive_threshold(edges_basic, percentile=80)
    
    # 5. 스케치 변환
    print("  5. 스케치 변환...")
    sketch = photo_to_sketch_hed(img, target_thickness=3.0, threshold=0.3)
    
    # 시각화
    fig, axes = plt.subplots(3, 3, figsize=(12, 12))
    axes = axes.ravel()
    
    # 원본
    axes[0].imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    axes[0].set_title('Original')
    axes[0].axis('off')
    
    # HED raw
    axes[1].imshow(edges_basic, cmap='gray')
    axes[1].set_title('HED (basic)')
    axes[1].axis('off')
    
    # HED multi-scale
    axes[2].imshow(edges_multi, cmap='gray')
    axes[2].set_title('HED (multi-scale)')
    axes[2].axis('off')
    
    # Threshold 결과들
    for idx, (name, result) in enumerate(results.items(), start=3):
        if idx < 8:
            axes[idx].imshow(result, cmap='gray')
            axes[idx].set_title(name)
            axes[idx].axis('off')
    
    # 최종 스케치
    axes[8].imshow(sketch, cmap='gray')
    axes[8].set_title('Final Sketch')
    axes[8].axis('off')
    
    plt.tight_layout()
    plt.savefig('/mnt/user-data/outputs/hed_comparison.png', dpi=150, bbox_inches='tight')
    print("✅ 결과 저장: /mnt/user-data/outputs/hed_comparison.png")
#!/usr/bin/env python3
"""
Structured Edge Detection (SED)
Microsoft에서 개발한 머신러닝 기반 엣지 검출

장점:
- 머신러닝 기반으로 더 정확한 엣지 검출
- 객체 경계를 잘 찾음
- 노이즈에 강함
- 연결성이 좋은 엣지

단점:
- 사전 학습된 모델 필요 (model.yml.gz)
- 처리 속도가 Canny보다 느림

모델 다운로드:
https://github.com/opencv/opencv_extra/tree/master/testdata/cv/ximgproc
파일: model.yml.gz
"""

import cv2
import numpy as np
import urllib.request
import os
from pathlib import Path


def download_sed_model(model_path: str = "./model.yml.gz") -> str:
    """
    SED 모델 자동 다운로드
    
    Args:
        model_path: 모델 저장 경로
    
    Returns:
        모델 파일 경로
    """
    if os.path.exists(model_path):
        print(f"✅ 모델이 이미 존재합니다: {model_path}")
        return model_path
    
    print("📥 SED 모델 다운로드 중...")
    url = "https://github.com/opencv/opencv_extra/raw/master/testdata/cv/ximgproc/model.yml.gz"
    
    try:
        urllib.request.urlretrieve(url, model_path)
        print(f"✅ 모델 다운로드 완료: {model_path}")
        return model_path
    except Exception as e:
        raise RuntimeError(f"❌ 모델 다운로드 실패: {e}")


def structured_edge_detection(
    img: np.ndarray,
    model_path: str = "./model.yml.gz",
    auto_download: bool = True
) -> np.ndarray:
    """
    Structured Edge Detection (기본)
    
    Args:
        img: 입력 이미지 (BGR)
        model_path: 모델 파일 경로
        auto_download: 모델 자동 다운로드 여부
    
    Returns:
        엣지 맵 (0.0~1.0, float32)
    """
    # opencv-contrib-python 설치 확인
    try:
        edge_detector = cv2.ximgproc.createStructuredEdgeDetection(model_path)
    except AttributeError:
        raise ImportError(
            "❌ opencv-contrib-python이 필요합니다.\n"
            "설치: pip install opencv-contrib-python --break-system-packages"
        )
    except cv2.error as e:
        if auto_download:
            # 모델 자동 다운로드 시도
            model_path = download_sed_model(model_path)
            edge_detector = cv2.ximgproc.createStructuredEdgeDetection(model_path)
        else:
            raise RuntimeError(f"❌ 모델을 로드할 수 없습니다: {e}")
    
    # 입력 이미지 정규화 (0.0~1.0)
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_float = img_rgb.astype(np.float32) / 255.0
    
    # 엣지 검출
    edges = edge_detector.detectEdges(img_float)
    
    return edges


def sed_with_nms(
    img: np.ndarray,
    model_path: str = "./model.yml.gz",
    auto_download: bool = True,
    nms_r: int = 2,
    nms_s: int = 0,
    nms_m: float = 1.0,
    is_parallel: bool = True
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Structured Edge Detection + Non-Maximum Suppression
    
    Args:
        img: 입력 이미지 (BGR)
        model_path: 모델 파일 경로
        auto_download: 모델 자동 다운로드 여부
        nms_r: NMS radius (2~4 추천)
        nms_s: NMS segment count (0=자동)
        nms_m: NMS multiplier (0.5~1.5)
        is_parallel: 병렬 처리 여부
    
    Returns:
        (raw_edges, nms_edges)
    """
    # 1. 기본 엣지 검출
    edges = structured_edge_detection(img, model_path, auto_download)
    
    # 2. NMS 적용
    try:
        edge_detector = cv2.ximgproc.createStructuredEdgeDetection(model_path)
        
        # Orientation 계산
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_float = img_rgb.astype(np.float32) / 255.0
        orientation = edge_detector.computeOrientation(edges)
        
        # NMS 적용
        nms_edges = edge_detector.edgesNms(
            edges, 
            orientation,
            r=nms_r,
            s=nms_s,
            m=nms_m,
            isParallel=is_parallel
        )
        
        return edges, nms_edges
        
    except Exception as e:
        print(f"⚠️  NMS 적용 실패: {e}")
        return edges, edges


def sed_to_binary(
    edges: np.ndarray,
    threshold: float = 0.1,
    max_val: int = 255
) -> np.ndarray:
    """
    SED 엣지 맵을 이진 이미지로 변환
    
    Args:
        edges: SED 엣지 맵 (0.0~1.0)
        threshold: 이진화 임계값 (0.0~1.0)
        max_val: 최댓값 (255)
    
    Returns:
        이진 이미지 (0 or max_val)
    """
    # 이진화
    binary = (edges > threshold).astype(np.uint8) * max_val
    return binary


def sed_adaptive_threshold(
    edges: np.ndarray,
    percentile: int = 70,
    max_val: int = 255
) -> np.ndarray:
    """
    Adaptive threshold를 사용한 이진화
    
    Args:
        edges: SED 엣지 맵
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
        threshold = 0.1
    
    binary = (edges > threshold).astype(np.uint8) * max_val
    return binary


def photo_to_sketch_sed(
    img: np.ndarray,
    target_thickness: float = 3.0,
    model_path: str = "./model.yml.gz",
    threshold: float = 0.08,
    use_nms: bool = True,
    nms_r: int = 2
) -> np.ndarray:
    """
    SED를 사용한 사진→스케치 변환
    (기존 photo_to_sketch 함수 대체)
    
    Args:
        img: 입력 이미지 (BGR)
        target_thickness: 목표 선 굵기
        model_path: SED 모델 경로
        threshold: 엣지 임계값 (0.05~0.15)
        use_nms: NMS 사용 여부
        nms_r: NMS radius
    
    Returns:
        스케치 이미지 (배경=255, 선=0)
    """
    # 1. SED 엣지 검출
    if use_nms:
        _, edges = sed_with_nms(img, model_path, auto_download=True, nms_r=nms_r)
    else:
        edges = structured_edge_detection(img, model_path, auto_download=True)
    
    # 2. 이진화
    binary = sed_to_binary(edges, threshold=threshold)
    
    # 3. Morphological closing (끊긴 선 연결)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
    connected = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel_close)
    
    # 4. 노이즈 제거
    kernel_open = np.ones((2,2), np.uint8)
    cleaned = cv2.morphologyEx(connected, cv2.MORPH_OPEN, kernel_open)
    
    # 5. 선 굵기 조정
    current_thickness = estimate_line_thickness(cleaned)
    
    if current_thickness > 0 and current_thickness < target_thickness:
        ratio = target_thickness / current_thickness
        kernel_size = max(3, min(7, int(ratio * 2) | 1))
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
# 테스트 코드
# =========================

if __name__ == "__main__":
    import matplotlib.pyplot as plt
    from typing import Tuple
    
    # opencv-contrib-python 확인
    try:
        import cv2.ximgproc
        print("✅ opencv-contrib-python 설치됨")
    except:
        print("❌ opencv-contrib-python 필요")
        print("설치: pip install opencv-contrib-python --break-system-packages")
        exit(1)
    
    # 테스트 이미지 로드
    img_path = "/mnt/user-data/uploads/3020040018820-reject-0_000.JPG"
    img = cv2.imread(img_path)
    
    if img is None:
        print("이미지를 찾을 수 없습니다.")
        exit(1)
    
    print("🔄 SED 엣지 검출 시작...")
    
    # 1. 기본 SED
    print("  1. 기본 SED...")
    edges_basic = structured_edge_detection(img, auto_download=True)
    
    # 2. SED + NMS
    print("  2. SED + NMS...")
    edges_raw, edges_nms = sed_with_nms(img, auto_download=True, nms_r=2)
    
    # 3. 여러 threshold 테스트
    print("  3. Threshold 테스트...")
    results = {}
    
    for thresh in [0.05, 0.08, 0.10, 0.15]:
        results[f'thresh_{thresh}'] = sed_to_binary(edges_nms, threshold=thresh)
    
    # 4. Adaptive threshold
    print("  4. Adaptive threshold...")
    results['adaptive'] = sed_adaptive_threshold(edges_nms, percentile=70)
    
    # 5. 스케치 변환
    print("  5. 스케치 변환...")
    sketch = photo_to_sketch_sed(img, target_thickness=3.0, threshold=0.08)
    
    # 시각화
    fig, axes = plt.subplots(3, 3, figsize=(12, 12))
    axes = axes.ravel()
    
    # 원본
    axes[0].imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    axes[0].set_title('Original')
    axes[0].axis('off')
    
    # SED raw
    axes[1].imshow(edges_basic, cmap='gray')
    axes[1].set_title('SED (raw)')
    axes[1].axis('off')
    
    # SED + NMS
    axes[2].imshow(edges_nms, cmap='gray')
    axes[2].set_title('SED + NMS')
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
    plt.savefig('/mnt/user-data/outputs/sed_comparison.png', dpi=150, bbox_inches='tight')
    print("✅ 결과 저장: /mnt/user-data/outputs/sed_comparison.png")
    
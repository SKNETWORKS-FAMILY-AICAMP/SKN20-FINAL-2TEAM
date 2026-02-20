#!/usr/bin/env python3
"""
Sobel + Hysteresis Thresholding Edge Detection
Canny와 유사하지만 더 세밀한 파라미터 제어 가능

장점:
- Gradient 계산 방식 선택 가능 (Sobel, Scharr, Prewitt)
- Hysteresis threshold를 수동으로 정밀 제어
- Non-maximum suppression 선택적 적용
- 엣지 연결 알고리즘 커스터마이징 가능
"""

import cv2
import numpy as np
from typing import Tuple, Optional


def sobel_gradient(img: np.ndarray, ksize: int = 3, method: str = 'sobel') -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Sobel/Scharr gradient 계산
    
    Args:
        img: 입력 이미지 (그레이스케일)
        ksize: 커널 크기 (3, 5, 7)
        method: 'sobel', 'scharr', 'prewitt'
    
    Returns:
        (gradient_magnitude, gradient_x, gradient_y)
    """
    if method == 'sobel':
        # Sobel operator
        grad_x = cv2.Sobel(img, cv2.CV_64F, 1, 0, ksize=ksize)
        grad_y = cv2.Sobel(img, cv2.CV_64F, 0, 1, ksize=ksize)
    
    elif method == 'scharr':
        # Scharr operator (더 정확, ksize=3 고정)
        grad_x = cv2.Scharr(img, cv2.CV_64F, 1, 0)
        grad_y = cv2.Scharr(img, cv2.CV_64F, 0, 1)
    
    elif method == 'prewitt':
        # Prewitt operator (custom kernel)
        kernel_x = np.array([[-1, 0, 1], [-1, 0, 1], [-1, 0, 1]], dtype=np.float64)
        kernel_y = np.array([[-1, -1, -1], [0, 0, 0], [1, 1, 1]], dtype=np.float64)
        grad_x = cv2.filter2D(img, cv2.CV_64F, kernel_x)
        grad_y = cv2.filter2D(img, cv2.CV_64F, kernel_y)
    
    else:
        raise ValueError(f"Unknown method: {method}")
    
    # Gradient magnitude
    gradient_magnitude = np.sqrt(grad_x**2 + grad_y**2)
    
    return gradient_magnitude, grad_x, grad_y


def non_maximum_suppression(gradient_mag: np.ndarray, 
                            grad_x: np.ndarray, 
                            grad_y: np.ndarray) -> np.ndarray:
    """
    Non-maximum suppression (NMS)
    Gradient 방향에서 최댓값만 남기고 나머지 제거
    
    Args:
        gradient_mag: Gradient magnitude
        grad_x: x방향 gradient
        grad_y: y방향 gradient
    
    Returns:
        NMS 적용된 gradient magnitude
    """
    H, W = gradient_mag.shape
    nms = np.zeros_like(gradient_mag)
    
    # Gradient 방향 계산 (0~180도)
    angle = np.arctan2(grad_y, grad_x) * 180 / np.pi
    angle[angle < 0] += 180  # 0~180도로 정규화
    
    # 4방향으로 양자화 (0°, 45°, 90°, 135°)
    for i in range(1, H-1):
        for j in range(1, W-1):
            theta = angle[i, j]
            mag = gradient_mag[i, j]
            
            # 이웃 픽셀 선택 (gradient 방향 기준)
            if (0 <= theta < 22.5) or (157.5 <= theta <= 180):
                # 0° (좌우)
                neighbors = [gradient_mag[i, j-1], gradient_mag[i, j+1]]
            elif 22.5 <= theta < 67.5:
                # 45° (좌하-우상)
                neighbors = [gradient_mag[i+1, j-1], gradient_mag[i-1, j+1]]
            elif 67.5 <= theta < 112.5:
                # 90° (상하)
                neighbors = [gradient_mag[i-1, j], gradient_mag[i+1, j]]
            else:  # 112.5 <= theta < 157.5
                # 135° (좌상-우하)
                neighbors = [gradient_mag[i-1, j-1], gradient_mag[i+1, j+1]]
            
            # 이웃보다 크면 유지, 작으면 제거
            if mag >= max(neighbors):
                nms[i, j] = mag
            else:
                nms[i, j] = 0
    
    return nms


def hysteresis_thresholding(gradient_mag: np.ndarray, 
                           low_threshold: float, 
                           high_threshold: float,
                           connectivity: int = 8) -> np.ndarray:
    """
    Hysteresis thresholding으로 엣지 연결
    
    Flow:
    1. Strong edges: gradient > high_threshold
    2. Weak edges: low_threshold <= gradient <= high_threshold
    3. Weak edge 중 strong edge와 연결된 것만 유지
    
    Args:
        gradient_mag: Gradient magnitude
        low_threshold: 낮은 임계값
        high_threshold: 높은 임계값
        connectivity: 연결성 (4 or 8)
    
    Returns:
        이진화된 엣지 이미지 (0 or 255)
    """
    H, W = gradient_mag.shape
    
    # 1. Strong / Weak edges 분류
    strong_mask = (gradient_mag >= high_threshold).astype(np.uint8)
    weak_mask = ((gradient_mag >= low_threshold) & (gradient_mag < high_threshold)).astype(np.uint8)
    
    # 2. Strong edges를 시드로 사용하여 연결된 weak edges 찾기
    # Morphological dilation으로 구현
    kernel_size = 3 if connectivity == 8 else 3  # 8-connectivity
    kernel = np.ones((kernel_size, kernel_size), np.uint8) if connectivity == 8 else \
             np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)  # 4-connectivity
    
    # Iterative dilation으로 연결된 weak edges 찾기
    edges = strong_mask.copy()
    iterations = 0
    max_iterations = 20  # 무한 루프 방지
    
    while iterations < max_iterations:
        # Strong edges를 확장
        dilated = cv2.dilate(edges, kernel, iterations=1)
        
        # Weak edges와 교집합 (연결된 weak edges만)
        connected_weak = dilated * weak_mask
        
        # 변화가 없으면 종료
        if np.array_equal(edges, edges + connected_weak):
            break
        
        # 연결된 weak edges 추가
        edges = edges + connected_weak
        edges = np.clip(edges, 0, 1).astype(np.uint8)
        
        iterations += 1
    
    # 3. 이진화 (0 or 255)
    edges = (edges * 255).astype(np.uint8)
    
    return edges


def sobel_hysteresis_edge_detection(
    img: np.ndarray,
    low_threshold: float = 30,
    high_threshold: float = 100,
    gaussian_ksize: int = 5,
    gaussian_sigma: float = 1.4,
    sobel_ksize: int = 3,
    gradient_method: str = 'sobel',
    use_nms: bool = True,
    connectivity: int = 8,
    normalize: bool = True
) -> np.ndarray:
    """
    Sobel + Hysteresis Thresholding 엣지 검출 (완전 제어 가능)
    
    Args:
        img: 입력 이미지 (BGR or 그레이스케일)
        low_threshold: Hysteresis 낮은 임계값
        high_threshold: Hysteresis 높은 임계값
        gaussian_ksize: Gaussian blur 커널 크기 (홀수)
        gaussian_sigma: Gaussian blur 표준편차
        sobel_ksize: Sobel 커널 크기 (3, 5, 7)
        gradient_method: 'sobel', 'scharr', 'prewitt'
        use_nms: Non-maximum suppression 사용 여부
        connectivity: Hysteresis 연결성 (4 or 8)
        normalize: Gradient magnitude 정규화 여부
    
    Returns:
        엣지 이미지 (0 or 255)
    """
    # 1. 그레이스케일 변환
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()
    
    # 2. Gaussian blur (노이즈 제거)
    if gaussian_ksize > 0:
        blurred = cv2.GaussianBlur(gray, (gaussian_ksize, gaussian_ksize), gaussian_sigma)
    else:
        blurred = gray
    
    # 3. Gradient 계산
    gradient_mag, grad_x, grad_y = sobel_gradient(blurred, sobel_ksize, gradient_method)
    
    # 4. Gradient 정규화 (선택)
    if normalize:
        gradient_mag = (gradient_mag / gradient_mag.max() * 255).astype(np.uint8)
    else:
        gradient_mag = np.clip(gradient_mag, 0, 255).astype(np.uint8)
    
    # 5. Non-maximum suppression (선택)
    if use_nms:
        gradient_mag = non_maximum_suppression(gradient_mag, grad_x, grad_y)
    
    # 6. Hysteresis thresholding
    edges = hysteresis_thresholding(gradient_mag, low_threshold, high_threshold, connectivity)
    
    return edges


def adaptive_sobel_hysteresis(
    img: np.ndarray,
    percentile_low: int = 10,
    percentile_high: int = 30,
    **kwargs
) -> np.ndarray:
    """
    Adaptive threshold를 사용한 Sobel + Hysteresis
    
    Args:
        img: 입력 이미지
        percentile_low: 낮은 임계값 백분위수 (0~100)
        percentile_high: 높은 임계값 백분위수 (0~100)
        **kwargs: sobel_hysteresis_edge_detection의 다른 파라미터
    
    Returns:
        엣지 이미지
    """
    # 1. 그레이스케일 변환
    if len(img.shape) == 3:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        gray = img.copy()
    
    # 2. Gaussian blur
    gaussian_ksize = kwargs.get('gaussian_ksize', 5)
    gaussian_sigma = kwargs.get('gaussian_sigma', 1.4)
    blurred = cv2.GaussianBlur(gray, (gaussian_ksize, gaussian_ksize), gaussian_sigma)
    
    # 3. Gradient 계산
    sobel_ksize = kwargs.get('sobel_ksize', 3)
    gradient_method = kwargs.get('gradient_method', 'sobel')
    gradient_mag, grad_x, grad_y = sobel_gradient(blurred, sobel_ksize, gradient_method)
    
    # 4. Adaptive threshold 계산 (백분위수 기반)
    # Gradient가 0인 픽셀 제외
    non_zero_grad = gradient_mag[gradient_mag > 0]
    
    if len(non_zero_grad) > 0:
        low_threshold = float(np.percentile(non_zero_grad, percentile_low))
        high_threshold = float(np.percentile(non_zero_grad, percentile_high))
    else:
        low_threshold = 30
        high_threshold = 100
    
    # 5. 나머지 처리
    return sobel_hysteresis_edge_detection(
        img,
        low_threshold=low_threshold,
        high_threshold=high_threshold,
        **kwargs
    )


# =========================
# 기존 코드에 통합하기 위한 래퍼 함수
# =========================

def photo_to_sketch_sobel(img: np.ndarray, target_thickness: float = 3.0) -> np.ndarray:
    """
    기존 photo_to_sketch 함수를 Sobel + Hysteresis로 대체
    """
    # Sobel + Hysteresis 엣지 검출 (adaptive)
    edges = adaptive_sobel_hysteresis(
        img,
        percentile_low=15,      # 낮은 임계값 백분위수
        percentile_high=35,     # 높은 임계값 백분위수
        gaussian_ksize=5,       # Gaussian blur
        gaussian_sigma=1.4,
        sobel_ksize=3,          # Sobel 커널
        gradient_method='sobel',  # Sobel operator
        use_nms=True,           # NMS 사용
        connectivity=8          # 8-connectivity
    )
    
    # 선 굵기 조정
    current_thickness = estimate_line_thickness(edges)
    
    if current_thickness > 0 and current_thickness < target_thickness:
        ratio = target_thickness / current_thickness
        kernel_size = max(3, min(7, int(ratio * 2) | 1))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        edges = cv2.dilate(edges, kernel, iterations=1)
    
    # 배경/선 반전 (배경=255, 선=0)
    sketch_final = 255 - edges
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
    
    # 테스트 이미지 로드
    img_path = "/mnt/user-data/uploads/3020040018820-reject-0_000.JPG"
    img = cv2.imread(img_path)
    
    if img is None:
        print("이미지를 찾을 수 없습니다.")
        exit(1)
    
    # 여러 파라미터 조합 테스트
    results = {}
    
    # 1. 기본 설정
    results['basic'] = sobel_hysteresis_edge_detection(
        img, low_threshold=30, high_threshold=100
    )
    
    # 2. Adaptive threshold
    results['adaptive'] = adaptive_sobel_hysteresis(
        img, percentile_low=15, percentile_high=35
    )
    
    # 3. Scharr gradient (더 정확)
    results['scharr'] = sobel_hysteresis_edge_detection(
        img, low_threshold=30, high_threshold=100, gradient_method='scharr'
    )
    
    # 4. NMS 없음 (선이 더 굵음)
    results['no_nms'] = sobel_hysteresis_edge_detection(
        img, low_threshold=30, high_threshold=100, use_nms=False
    )
    
    # 5. 높은 threshold (강한 엣지만)
    results['high_thresh'] = sobel_hysteresis_edge_detection(
        img, low_threshold=60, high_threshold=150
    )
    
    # 6. 낮은 threshold (많은 엣지)
    results['low_thresh'] = sobel_hysteresis_edge_detection(
        img, low_threshold=15, high_threshold=50
    )
    
    # 시각화
    fig, axes = plt.subplots(2, 4, figsize=(16, 8))
    axes = axes.ravel()
    
    # 원본
    axes[0].imshow(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    axes[0].set_title('Original')
    axes[0].axis('off')
    
    # 결과들
    for idx, (name, result) in enumerate(results.items(), start=1):
        axes[idx].imshow(result, cmap='gray')
        axes[idx].set_title(name)
        axes[idx].axis('off')
    
    # 마지막 서브플롯 숨기기
    axes[-1].axis('off')
    
    plt.tight_layout()
    plt.savefig('/mnt/user-data/outputs/sobel_hysteresis_comparison.png', 
                dpi=150, bbox_inches='tight')
    print("✅ 결과 저장: /mnt/user-data/outputs/sobel_hysteresis_comparison.png")
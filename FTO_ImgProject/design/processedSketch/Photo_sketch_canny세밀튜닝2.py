#!/usr/bin/env python3
"""
🎨 배치 이미지 처리기 - 최종 통합 버전 (V4 Final)

핵심 기능:
1. 정교한 이미지 분류 (V3 알고리즘)
   - 채도 기반 컬러 사진 감지
   - 그라데이션 부드러움으로 조명/반사 감지
   - 히스토그램 엔트로피로 톤 다양성 측정
   
2. 자동 이미지 처리 (V4 기능)
   - 사진 → 스케치 변환 (XDoG 알고리즘)
   - 선 굵기 자동 감지 및 조정
   - 굵은 선 세밀화 (→ 목표 굵기)
   - 얇은 선 보강 (가독성 향상)

3. 안전한 파일 관리
   - 원본 자동 백업 (backup_original/)
   - 처리된 파일 저장 (processed_sketches/)
   - 상세 처리 로그 생성

사용법:
    python Photo_sketch_v2.py <폴더경로> [옵션]

옵션:
    --force                확인 없이 즉시 처리
    --target-thickness N   목표 선 굵기 (기본값: 3 픽셀)
    --delete-photos        사진 원본 삭제 (기존 V3 동작)

예시:
    python Photo_sketch_v2.py ./images
    python Photo_sketch_v2.py ./images --target-thickness 2.5
    python Photo_sketch_v2.py ./images --force --delete-photos
"""

"""
🎨 배치 이미지 처리기 - 최종 통합 버전 (V4 Final)
사진을 스케치로 변환하고 선 굵기를 조정하는 도구

## ⚠️ 중요 사항

1. **백업은 항상 수행**: `--delete-photos` 옵션 여부와 관계없이 모든 파일이 `backup_original/`에 백업됩니다.

2. **삭제는 옵션**: `--delete-photos` 플래그를 사용해야만 원본 사진이 삭제됩니다.

3. **스케치는 유지**: 스케치로 분류된 파일은 원본 디렉토리에서 삭제되지 않습니다.

4. **최종 구조**:
```
./images/
├── backup_original/      # 모든 원본 파일
├── processed_sketches/   # 처리된 스케치 (사진→변환 포함)
├── sketch1.jpg           # 스케치 원본 유지
└── process_log.json      # 처리 로그

"""

import cv2  # OpenCV: 이미지 처리 라이브러리
import numpy as np  # NumPy: 배열 연산 라이브러리
import sys  # 시스템 관련 (명령줄 인자)
import os  # 파일/디렉토리 작업
from pathlib import Path  # 경로 객체 처리
from dataclasses import dataclass  # 데이터 클래스 정의
from typing import Tuple, List, Optional  # 타입 힌트
import time  # 시간 관련
import json  # JSON 파일 처리
import shutil  # 파일 복사/이동


@dataclass
class ImageFeatures:
    """이미지 특징값을 저장하는 데이터 클래스"""
    # 기본 특징
    extreme_pixels_ratio: float  # 극값 픽셀 비율 (매우 밝거나 어두운 픽셀)
    midtone_ratio: float  # 중간톤 비율
    foreground_ratio: float  # 전경 비율
    is_grayscale: bool  # 흑백 이미지 여부
    texture_complexity: float  # 텍스처 복잡도
    
    # 사진 감지 특징
    saturation_mean: float  # 채도 평균 (컬러 감지)
    saturation_std: float  # 채도 표준편차
    smooth_gradient_ratio: float  # 부드러운 그라데이션 비율 (사진의 조명/반사)
    hist_entropy: float  # 히스토그램 엔트로피 (톤의 다양성)
    edge_ratio: float  # 엣지 비율 (선의 밀도)
    bg_brightness: float  # 배경 밝기
    
    # 선 굵기 특징
    avg_line_thickness: float  # 평균 선 굵기 (픽셀)
    
    # 점수
    sketch_score: float = 0.0  # 스케치 점수 (높을수록 스케치)
    photo_score: float = 0.0  # 사진 점수 (높을수록 사진)
    final_score: float = 0.0  # 최종 점수 (sketch - photo)
    confidence: float = 0.0  # 신뢰도 (절댓값)


@dataclass
class ProcessResult:
    """처리 결과를 저장하는 데이터 클래스"""
    filename: str  # 파일명
    original_classification: str  # 원본 분류 ("photo" or "sketch")
    original_type: str  # 세부 타입 ("photo", "thick_sketch", "thin_sketch", "normal_sketch")
    action: str  # 수행된 작업 ("photo_to_sketch", "thinned", "thickened", "kept", "deleted")
    final_score: float  # 분류 점수
    confidence: float  # 신뢰도
    avg_line_thickness_before: float  # 처리 전 선 굵기
    avg_line_thickness_after: float  # 처리 후 선 굵기
    size_bytes: int = 0  # 파일 크기
    backup_path: str = ""  # 백업 경로
    output_path: str = ""  # 출력 경로
    error: str = ""  # 에러 메시지


def estimate_line_thickness(edges: np.ndarray, percentile: int = 75) -> float:
    """
    엣지 이미지에서 평균 선 굵기 추정
    
    원리:
    1. Distance Transform으로 각 엣지 픽셀에서 가장 가까운 비엣지까지 거리 계산
    2. 거리의 percentile × 2 = 선 굵기
    
    Args:
        edges: 엣지 이미지 (255=엣지, 0=배경)
        percentile: 백분위수 (기본 75)
    
    Returns:
        평균 선 굵기 (픽셀)
    """
    # 엣지가 없으면 0 반환
    if np.sum(edges) == 0:
        return 0.0
    
    # Distance Transform: 각 흰색 픽셀에서 가장 가까운 검은색 픽셀까지의 거리 계산
    dist_transform = cv2.distanceTransform(edges, cv2.DIST_L2, 5)
    
    # 엣지 픽셀 위치에서의 거리값만 추출
    edge_distances = dist_transform[edges > 0]
    
    # 거리값이 없으면 0 반환
    if len(edge_distances) == 0:
        return 0.0
    
    # 백분위수 기반으로 평균 선 굵기 계산 (이상치 제거)
    # 거리 × 2 = 선의 전체 굵기 (양쪽 방향)
    thickness = float(np.percentile(edge_distances, percentile) * 2)
    
    return thickness


def classify_image(img_path: str) -> Tuple[str, float, float, ImageFeatures]:
    """
    이미지를 분류: 사진 vs 스케치
    
    Flow:
    1. 이미지 읽기
    2. 11가지 특징 추출
    3. 스케치 점수 / 사진 점수 계산
    4. 최종 판정
    
    Returns:
        (분류결과, 최종점수, 신뢰도, 특징값)
    """
    # 이미지 읽기 (BGR 컬러)
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"이미지를 읽을 수 없습니다: {img_path}")
    
    # 그레이스케일 변환 (명암 분석용)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # ========== 특징 추출 (11개) ==========
    
    # 특징 1: 색상 정보 (채도)
    img_hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)  # HSV 색공간 변환
    h, s, v = cv2.split(img_hsv)  # H(색상), S(채도), V(명도) 분리
    saturation_mean = float(np.mean(s))  # 평균 채도 (컬러 사진일수록 높음)
    saturation_std = float(np.std(s))  # 채도 표준편차
    
    # 특징 2: 그레이스케일 여부 (RGB 채널 차이)
    b, g, r = cv2.split(img)  # BGR 채널 분리
    # R-G 차이 + G-B 차이
    channel_diff = np.mean(np.abs(r.astype(float) - g.astype(float))) + \
                   np.mean(np.abs(g.astype(float) - b.astype(float)))
    is_grayscale = bool(channel_diff < 10.0)  # 차이가 작으면 흑백
    
    # 특징 3: 극값 픽셀 비율 (매우 밝거나 어두운 픽셀)
    very_dark = np.sum(gray < 50) / gray.size  # 매우 어두운 픽셀 (<50)
    very_bright = np.sum(gray > 200) / gray.size  # 매우 밝은 픽셀 (>200)
    extreme_pixels = float(very_dark + very_bright)  # 극값 픽셀 총 비율
    
    # 특징 4: 중간톤 비율
    midtone = float(np.sum((gray >= 50) & (gray <= 200)) / gray.size)
    
    # 특징 5: 전경 비율 (Otsu 이진화)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    foreground = float(np.sum(binary < 128) / binary.size)  # 어두운 부분 = 전경
    
    # 특징 6: 엣지 밀도 (Canny 엣지 검출)
    edges = cv2.Canny(gray, 50, 150)  # 엣지 검출 (임계값 50~150)
    edge_ratio = float(np.sum(edges > 0) / edges.size)  # 엣지 픽셀 비율
    
    # 특징 7: 선 굵기 추정
    avg_line_thickness = estimate_line_thickness(edges)
    
    # 특징 8: 텍스처 복잡도 (Laplacian 분산)
    laplacian = cv2.Laplacian(gray, cv2.CV_64F)  # 2차 미분 (엣지 강조)
    texture = float(np.var(laplacian))  # 분산이 클수록 복잡한 텍스처
    
    # 특징 9: 그라데이션 부드러움 (Sobel 그래디언트)
    gradient_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=5)  # x방향 그래디언트
    gradient_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=5)  # y방향 그래디언트
    gradient_mag = np.sqrt(gradient_x**2 + gradient_y**2)  # 그래디언트 크기
    smooth_gradient = float(np.sum(gradient_mag < 10) / gradient_mag.size)  # 부드러운 영역 비율
    
    # 특징 10: 배경 밝기
    bright_pixels = gray[gray > 200]  # 밝은 픽셀만 추출
    bg_brightness = float(np.mean(bright_pixels)) if len(bright_pixels) > 0 else 0.0
    
    # 특징 11: 히스토그램 엔트로피 (톤의 다양성)
    hist = cv2.calcHist([gray], [0], None, [256], [0, 256])  # 명도 히스토그램
    hist_norm = hist.flatten() / (hist.sum() + 1e-10)  # 정규화
    hist_entropy = float(-np.sum(hist_norm * np.log2(hist_norm + 1e-10)))  # 엔트로피 계산
    
    # ========== 점수 계산 ==========
    
    sketch_score = 0.0  # 스케치 점수 (0~1)
    photo_score = 0.0  # 사진 점수 (0~1)
    
    # === 사진 지표 체크 ===
    
    # 사진 지표 1: 채도 (컬러 사진)
    if saturation_mean > 15:  # 채도가 높으면
        photo_score += 0.4  # 강력한 사진 지표
    elif saturation_mean > 5:  # 채도가 약간 있으면
        photo_score += 0.3  # 중간 사진 지표
    elif saturation_mean >2:
        photo_score += 0.15
    
    # 사진 지표 2: 부드러운 그라데이션 (조명/반사)
    if smooth_gradient > 0.65:  # 그라데이션이 매우 부드러우면
        photo_score += 0.25  # 사진 특징
    elif smooth_gradient > 0.55:  # 그라데이션이 부드러우면
        photo_score += 0.15  # 약한 사진 특징
    elif smooth_gradient > 0.4: # 그라데이션이 약간 부드러우면
        photo_score += 0.1 # 투명 제품 사진 특수 감지
    
    # 사진 지표 3: 히스토그램 엔트로피 (톤의 다양성)
    if hist_entropy > 6.5:  # 엔트로피가 높으면 (톤이 다양)
        photo_score += 0.2  # 사진 특징
    elif hist_entropy > 5.5:
        photo_score += 0.1
    
    # 사진 지표 4: 중간톤이 많음
    if midtone > 0.5:  # 중간톤이 50% 이상
        photo_score += 0.15  # 사진 특징
    
    # 사진 지표 5: 🆕 무채색 제품 사진 특수 처리
    # 엣지가 거의 없고 + 그라데이션이 부드러우면 = 제품 사진
    if edge_ratio < 0.01 and smooth_gradient > 0.7:
        photo_score += 0.3  # 강력한 사진 지표
    
    # === 스케치 지표 체크 ===
    
    # 스케치 지표 1: 그레이스케일 (흑백)
    # 단, 그라데이션이 부드럽지 않아야 함 (제품 사진 제외)
    if is_grayscale and smooth_gradient < 0.5:
        sketch_score += 0.15  # 스케치 특징
    
    # 스케치 지표 2: 극값 픽셀 비율 (흑백 대비)
    # 단, 엣지가 있어야 진짜 스케치 (제품 사진 제외)
    if 0.7 < extreme_pixels < 0.95 and edge_ratio > 0.02:
        sketch_score += 0.2  # 강한 스케치 특징
    elif extreme_pixels >= 0.95 and edge_ratio > 0.01:
        sketch_score += 0.1  # 약한 스케치 특징
    
    # 스케치 지표 3: 중간톤이 적음
    # 단, 엣지가 있어야 함
    if midtone < 0.1 and edge_ratio > 0.02:
        sketch_score += 0.15  # 강한 스케치 특징
    elif midtone < 0.2 and edge_ratio > 0.02:
        sketch_score += 0.08  # 약한 스케치 특징
    
    # 스케치 지표 4: 엣지 비율 (선 중심)
    if 0.02 < edge_ratio < 0.15:  # 적당한 엣지 밀도
        sketch_score += 0.15  # 스케치의 핵심 특징
    elif edge_ratio >= 0.15:  # 엣지가 너무 많으면
        sketch_score += 0.05  # 약한 점수
    
    # 스케치 지표 5: 텍스처가 단순
    if texture < 80:  # 텍스처가 매우 단순
        sketch_score += 0.1
    elif texture < 150:  # 텍스처가 단순
        sketch_score += 0.05
    
    # 스케치 지표 6: 배경이 매우 밝음 (흰 종이)
    # 단, 엣지가 있어야 함
    if bg_brightness > 240 and edge_ratio > 0.02:
        sketch_score += 0.1  # 스케치 특징
    
    # ========== 최종 판정 ==========
    
    final_score = sketch_score - photo_score  # 최종 점수 (양수=스케치, 음수=사진)
    confidence = abs(final_score)  # 신뢰도 (절댓값)
    
    # 점수 기준으로 분류
    if final_score > 0.15:  # 스케치 점수가 0.15 이상 높으면
        classification = "sketch"
    elif final_score < -0.15:  # 사진 점수가 0.15 이상 높으면
        classification = "photo"
    else:  # 경계 케이스 (-0.15 ~ 0.15)
        # 추가 휴리스틱 적용
        if saturation_mean > 5:  # 채도가 조금이라도 있으면
            classification = "photo"  # 사진으로 분류
        elif edge_ratio > 0.05 and is_grayscale:  # 엣지가 있고 흑백이면
            classification = "sketch"  # 스케치로 분류
        else:
            # 불확실하면 보수적으로 스케치 유지
            classification = "sketch"
    
    # 특징값 객체 생성
    features = ImageFeatures(
        extreme_pixels_ratio=extreme_pixels,
        midtone_ratio=midtone,
        foreground_ratio=foreground,
        is_grayscale=is_grayscale,
        texture_complexity=texture,
        saturation_mean=saturation_mean,
        saturation_std=saturation_std,
        smooth_gradient_ratio=smooth_gradient,
        hist_entropy=hist_entropy,
        edge_ratio=edge_ratio,
        bg_brightness=bg_brightness,
        avg_line_thickness=avg_line_thickness,
        sketch_score=sketch_score,
        photo_score=photo_score,
        final_score=final_score,
        confidence=confidence
    )
    
    return classification, final_score, confidence, features


def photo_to_sketch(img: np.ndarray, target_thickness: float = 3.0) -> np.ndarray:
    """
    개선된 사진→스케치 변환 (adaptive Canny + multi-scale)
    
    개선 사항:
    1. CLAHE로 명암 대비 강화
    2. Bilateral filter로 노이즈 제거 (엣지 보존)
    3. Otsu 기반 adaptive threshold
    4. Multi-scale Canny 결합
    5. Morphological closing으로 끊긴 선 연결
    """
    # 그레이스케일 변환
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
    
    # 1. CLAHE로 명암 대비 강화 (반사/투명 영역 개선)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    
    # 2. Bilateral filter (엣지 보존 노이즈 제거)
    denoised = cv2.bilateralFilter(enhanced, d=9, sigmaColor=75, sigmaSpace=75)
    
    # 3. Adaptive threshold 계산 (Otsu + median 기반)
    # 전체 이미지의 median을 기준으로 threshold 자동 계산
    v = np.median(denoised)
    sigma = 0.33  # threshold 범위 조절 (0.2~0.5)
    
    lower = int(max(0, (1.0 - sigma) * v))
    upper = int(min(255, (1.0 + sigma) * v))
    
    # 4. Multi-scale Canny (3가지 스케일)
    edges_list = []
    
    # Fine scale (세밀한 디테일)
    edges_fine = cv2.Canny(denoised, lower, upper, apertureSize=3, L2gradient=True)
    edges_list.append(edges_fine)
    
    # Medium scale (중간 구조)
    blurred_medium = cv2.GaussianBlur(denoised, (5,5), 1.0)
    edges_medium = cv2.Canny(blurred_medium, 
                            int(lower*1.2), int(upper*1.2), 
                            apertureSize=5, L2gradient=True)
    edges_list.append(edges_medium)
    
    # Coarse scale (큰 구조)
    blurred_coarse = cv2.GaussianBlur(denoised, (9,9), 2.0)
    edges_coarse = cv2.Canny(blurred_coarse, 
                            int(lower*1.5), int(upper*1.5), 
                            apertureSize=7, L2gradient=True)
    edges_list.append(edges_coarse)
    
    # 5. Multi-scale 결합 (maximum)
    edges_combined = np.maximum.reduce(edges_list)
    
    # 6. Morphological closing (끊긴 선 연결)
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
    edges_connected = cv2.morphologyEx(edges_combined, cv2.MORPH_CLOSE, kernel_close)
    
    # 7. 노이즈 제거 (작은 점 제거)
    kernel_open = np.ones((2,2), np.uint8)
    edges_cleaned = cv2.morphologyEx(edges_connected, cv2.MORPH_OPEN, kernel_open)
    
    # 8. 선 굵기 조정
    current_thickness = estimate_line_thickness(edges_cleaned)
    
    if current_thickness > 0 and current_thickness < target_thickness:
        ratio = target_thickness / current_thickness
        kernel_size = max(3, min(7, int(ratio * 2) | 1))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        edges_final = cv2.dilate(edges_cleaned, kernel, iterations=1)
    else:
        edges_final = edges_cleaned
    
    # 9. 반전 및 이진화 (배경=255, 선=0)
    sketch_final = 255 - edges_final
    sketch_final = np.where(sketch_final > 127, 255, 0).astype(np.uint8)
    
    return sketch_final


# classify_image 함수 내의 Canny 부분도 개선
def classify_image_enhanced(img_path: str) -> Tuple[str, float, float, ImageFeatures]:
    """
    개선된 이미지 분류 (adaptive Canny)
    """
    img = cv2.imread(img_path)
    if img is None:
        raise FileNotFoundError(f"이미지를 읽을 수 없습니다: {img_path}")
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # CLAHE + Bilateral filter 전처리
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(gray)
    denoised = cv2.bilateralFilter(enhanced, 9, 75, 75)
    
    # Adaptive threshold 계산
    v = np.median(denoised)
    sigma = 0.33
    lower = int(max(0, (1.0 - sigma) * v))
    upper = int(min(255, (1.0 + sigma) * v))
    
    # Canny 엣지 검출 (L2 gradient 사용)
    edges = cv2.Canny(denoised, lower, upper, L2gradient=True)
    
    # ... 나머지 특징 추출 코드 동일 ...
    
    edge_ratio = float(np.sum(edges > 0) / edges.size)
    avg_line_thickness = estimate_line_thickness(edges)
    
    # ... 나머지 코드 동일 ...


def adjust_line_thickness(img: np.ndarray, target_thickness: float = 3.0) -> np.ndarray:
    """
    스케치 선 굵기 조정 → 흰색 배경(255) + 검정색 선(0)
    
    Flow:
    1. 그레이스케일 변환
    2. Otsu 이진화
    3. 배경/선 방향 확인 및 정규화
    4. 선 굵기 측정
    5. Dilation/Erosion으로 굵기 조정
    6. 배경/선 반전 및 완전 이진화
    
    Args:
        img: 입력 스케치 이미지
        target_thickness: 목표 선 굵기 (기본 3픽셀)
    
    Returns:
        조정된 스케치 (배경=255, 선=0)
    """
    # 그레이스케일 변환
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
    
    # Otsu 이진화 (자동 임계값 결정)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    # 어두운 부분과 밝은 부분 비율 확인
    dark_ratio = np.sum(binary < 128) / binary.size  # 어두운 픽셀 비율
    bright_ratio = np.sum(binary >= 128) / binary.size  # 밝은 픽셀 비율
    
    # 배경이 어두운 경우 반전 (배경을 항상 밝게 만듦)
    if dark_ratio > bright_ratio:
        binary = 255 - binary  # 반전
    
    # 이제 binary는: 배경=255(밝음), 선=0(어두움)
    
    # 선 영역 추출 (선=255로 변환하여 처리)
    lines = 255 - binary  # 반전: 선=255, 배경=0
    
    # 현재 선 굵기 측정
    current_thickness = estimate_line_thickness(lines)
    
    if current_thickness == 0:
        # 선이 거의 없는 경우 - 원본을 배경=255, 선=0으로 반환
        result = binary
    else:
        # 굵기 비율 계산
        ratio = target_thickness / current_thickness
        
        if ratio > 1.2:  # 목표가 현재보다 1.2배 이상 굵으면
            # Dilation (선 굵게 만들기)
            iterations = max(1, min(3, int(ratio - 1)))  # 반복 횟수 (1~3회)
            kernel_size = max(3, min(7, int(ratio * 2) | 1))  # 커널 크기 (3~7, 홀수)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
            lines_adjusted = cv2.dilate(lines, kernel, iterations=iterations)
            
        elif ratio < 0.8:  # 목표가 현재보다 0.8배 이하로 얇으면
            # Erosion (선 얇게 만들기)
            iterations = max(1, min(3, int(1 / ratio - 1)))  # 반복 횟수
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))  # 3x3 커널
            lines_adjusted = cv2.erode(lines, kernel, iterations=iterations)
            
            # 너무 얇아진 경우 보정
            new_thickness = estimate_line_thickness(lines_adjusted)
            if new_thickness > 0 and new_thickness < target_thickness * 0.7:
                # 목표의 70% 미만이면 다시 굵게
                lines_adjusted = cv2.dilate(lines_adjusted, kernel, iterations=1)
        else:
            # 적절한 굵기 (0.8 ~ 1.2배)
            lines_adjusted = lines  # 그대로 유지
        
        # 최종: 배경=255(흰색), 선=0(검정)
        result = 255 - lines_adjusted  # 반전
    
    # 완전 이진화 (0 또는 255만)
    result = np.where(result > 127, 255, 0).astype(np.uint8)
    
    # 3채널로 변환 (원본이 컬러였으면)
    if len(img.shape) == 3:
        result = cv2.cvtColor(result, cv2.COLOR_GRAY2BGR)
    
    return result


def process_image(img_path: str, backup_dir: str, output_dir: str, 
                  target_thickness: float = 5.0, delete_photos: bool = False) -> ProcessResult:
    """
    이미지 처리 메인 함수
    
    Flow:
    1. 이미지 분류 (사진 vs 스케치)
    2. 원본 백업
    3. 처리 결정 (사진→스케치, 선 굵기 조정, 유지)
    4. 처리 실행
    5. 완전 이진화 후 저장
    6. 결과 반환
    
    Returns:
        ProcessResult 객체 (처리 결과 정보)
    """
    filename = Path(img_path).name  # 파일명 추출
    
    try:
        # 1. 이미지 분류
        classification, final_score, confidence, features = classify_image(img_path)
        
        # 이미지 로드
        img = cv2.imread(img_path)
        if img is None:
            raise FileNotFoundError(f"이미지를 읽을 수 없습니다: {img_path}")
        
        # 파일 정보
        size_bytes = os.path.getsize(img_path)  # 파일 크기
        thickness_before = features.avg_line_thickness  # 처리 전 선 굵기
        
        # 2. 원본 백업 (항상 수행)
        backup_path = os.path.join(backup_dir, filename)
        shutil.copy2(img_path, backup_path)  # 메타데이터 포함 복사
        
        # 3. 처리 결정
        if classification == "photo":
            # 사진 → 스케치 변환
            processed = photo_to_sketch(img, target_thickness)
            action = "photo_to_sketch"
            original_type = "photo"
            # delete_photos 옵션은 나중에 처리 (변환 후 삭제)
            
        elif features.avg_line_thickness > 5.0:
            # 굵은 스케치 (5px 초과) → 세밀화
            processed = adjust_line_thickness(img, target_thickness)
            action = "thinned"
            original_type = "thick_sketch"
            
        elif features.avg_line_thickness < 4.0 and features.avg_line_thickness > 0:
            # 얇은 스케치 (4px 미만) → 굵기 보강
            processed = adjust_line_thickness(img, target_thickness)
            action = "thickened"
            original_type = "thin_sketch"
            
        else:
            # 적절한 스케치 (2~5px) → 유지
            processed = img
            action = "kept"
            original_type = "normal_sketch"
        
        # 4. 처리 후 선 굵기 측정
        if action != "kept" and action != "deleted":
            # 처리된 이미지의 선 굵기 재측정
            gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY) if len(processed.shape) == 3 else processed
            edges = cv2.Canny(gray, 50, 150)
            thickness_after = estimate_line_thickness(edges)
        else:
            # 유지 또는 삭제 예약인 경우 그대로
            thickness_after = thickness_before
        
        # 5. 저장
        if action != "deleted":
            output_path = os.path.join(output_dir, filename)
            
            # 완전 이진화 보장 (0 또는 255만)
            if len(processed.shape) == 3:
                # 컬러 이미지인 경우
                processed_gray = cv2.cvtColor(processed, cv2.COLOR_BGR2GRAY)  # 그레이스케일 변환
                processed_binary = np.where(processed_gray >= 127, 255, 0).astype(np.uint8)  # 이진화
                processed_final = cv2.cvtColor(processed_binary, cv2.COLOR_GRAY2BGR)  # 다시 3채널로
            else:
                # 그레이스케일 이미지인 경우
                processed_final = np.where(processed >= 127, 255, 0).astype(np.uint8)  # 이진화
            
            cv2.imwrite(output_path, processed_final)  # 파일 저장
        else:
            # 삭제 예약된 경우 출력 경로 없음
            output_path = ""
        
        # 6. 결과 객체 생성
        result = ProcessResult(
            filename=filename,
            original_classification=classification,
            original_type=original_type,
            action=action,
            final_score=final_score,
            confidence=confidence,
            avg_line_thickness_before=thickness_before,
            avg_line_thickness_after=thickness_after,
            size_bytes=size_bytes,
            backup_path=backup_path,
            output_path=output_path
        )
        
        return result
        
    except Exception as e:
        # 에러 발생 시 에러 결과 반환
        return ProcessResult(
            filename=filename,
            original_classification="error",
            original_type="error",
            action="error",
            final_score=0.0,
            confidence=0.0,
            avg_line_thickness_before=0,
            avg_line_thickness_after=0,
            error=str(e)
        )


def find_images(input_dir: str) -> List[str]:
    """
    디렉토리에서 이미지 파일 찾기
    
    지원 확장자: .jpg, .jpeg, .png, .bmp (대소문자 무관)
    
    Returns:
        이미지 파일 경로 리스트 (정렬됨)
    """
    # 지원하는 이미지 확장자
    image_extensions = {'.jpg', '.jpeg', '.png', '.JPG', '.JPEG', '.PNG', '.bmp', '.BMP'}
    image_files = []
    
    # Path 객체 생성
    input_path = Path(input_dir)
    if not input_path.exists():
        raise FileNotFoundError(f"디렉토리를 찾을 수 없습니다: {input_dir}")
    
    # 각 확장자별로 파일 검색
    for ext in image_extensions:
        image_files.extend(input_path.glob(f"*{ext}"))  # 와일드카드 검색
    
    # 정렬하여 반환 (파일명 기준)
    return sorted([str(f) for f in image_files])


def process_batch(input_dir: str, target_thickness: float = 3.0, 
                  delete_photos: bool = False, force: bool = False) -> List[ProcessResult]:
    """
    배치 처리 메인 함수
    
    Flow:
    1. 디렉토리 생성 (backup, output)
    2. 이미지 파일 검색
    3. 사용자 확인 (force 옵션이 아닐 경우)
    4. 각 이미지 처리
    5. 사진 원본 삭제 (옵션)
    6. 통계 출력
    
    Returns:
        처리 결과 리스트
    """
    # 1. 디렉토리 설정
    backup_dir = os.path.join(input_dir, "backup_original")  # 백업 폴더
    output_dir = os.path.join(input_dir, "processed_sketches")  # 출력 폴더
    os.makedirs(backup_dir, exist_ok=True)  # 폴더 생성 (이미 있으면 무시)
    os.makedirs(output_dir, exist_ok=True)
    
    # 2. 이미지 파일 검색
    image_files = find_images(input_dir)
    
    if not image_files:
        print(f"⚠️  경고: {input_dir}에서 이미지를 찾을 수 없습니다.")
        return []
    
    # 헤더 출력
    print(f"\n{'='*80}")
    print(f"🎨 배치 이미지 처리기 - 최종 통합 버전 (V4 Final)")
    print(f"{'='*80}")
    print(f"📁 입력 디렉토리: {input_dir}")
    print(f"💾 백업 디렉토리: {backup_dir}")
    print(f"📤 출력 디렉토리: {output_dir}")
    print(f"🎯 목표 선 굵기: {target_thickness} px")
    print(f"🗑️  사진 원본 삭제: {'예' if delete_photos else '아니오'}")
    print(f"🖼️  발견된 이미지: {len(image_files)}개")
    print(f"{'='*80}\n")
    
    # 3. 사용자 확인
    if not force:
        print(f"⚠️  처리를 시작하시겠습니까? (y/n): ", end="", flush=True)
        response = input().strip().lower()  # 입력 받기
        if response != "y":
            print(f"\n❌ 처리가 취소되었습니다.\n")
            return []
    else:
        print(f"🔄 --force 옵션으로 즉시 처리합니다.\n")
    
    # 4. 배치 처리
    results = []  # 결과 저장 리스트
    
    print(f"{'='*80}")
    print(f"🔄 이미지 처리 중...\n")
    
    # 각 이미지 처리
    for i, img_path in enumerate(image_files, 1):
        filename = Path(img_path).name
        print(f"[{i}/{len(image_files)}] 처리 중: {filename}")
        
        # 이미지 처리 실행
        result = process_image(img_path, backup_dir, output_dir, target_thickness, delete_photos)
        results.append(result)
        
        # 결과 출력
        if result.error:
            # 에러 발생
            print(f"  ❌ 오류: {result.error}\n")
        else:
            # 정상 처리
            # 아이콘 매핑
            icon_map = {
                "photo": "📸",
                "thick_sketch": "📏",
                "thin_sketch": "✏️",
                "normal_sketch": "✅"
            }
            # 작업 텍스트 매핑
            action_map = {
                "photo_to_sketch": "사진→스케치 변환",
                "thinned": "선 세밀화",
                "thickened": "선 굵기 보강",
                "kept": "유지됨",
                "deleted": "백업 후 삭제"
            }
            
            icon = icon_map.get(result.original_type, "❓")
            action_text = action_map.get(result.action, result.action)
            
            # 결과 정보 출력
            print(f"  {icon} {result.original_classification.upper()}")
            print(f"     타입: {result.original_type}")
            print(f"     처리: {action_text}")
            print(f"     점수: {result.final_score:+.3f} (신뢰도: {result.confidence:.3f})")
            print(f"     선 굵기: {result.avg_line_thickness_before:.2f}px → {result.avg_line_thickness_after:.2f}px")
            if result.output_path:
                print(f"     출력: {result.output_path}")
            print()
    
    # 5. 사진 원본 삭제 (옵션)
    if delete_photos:
        print(f"{'='*80}")
        print(f"🗑️  사진 원본 삭제 중...\n")
        
        deleted_count = 0
        for result in results:
            # 사진으로 분류되었고 백업이 있으면
            if result.original_classification == "photo" and result.backup_path:
                img_path = os.path.join(input_dir, result.filename)
                if os.path.exists(img_path):
                    try:
                        os.remove(img_path)  # 파일 삭제
                        print(f"  ✅ 삭제됨: {result.filename}")
                        deleted_count += 1
                    except Exception as e:
                        print(f"  ❌ 삭제 실패: {result.filename} ({e})")
        
        print(f"\n  총 {deleted_count}개 사진 원본 삭제됨\n")
    
    # 6. 통계 출력
    print(f"{'='*80}")
    print(f"📊 처리 완료 요약")
    print(f"{'='*80}")
    
    # 통계 계산
    total = len(results)
    photos = sum(1 for r in results if r.original_classification == "photo")
    sketches = sum(1 for r in results if r.original_classification == "sketch")
    thick = sum(1 for r in results if r.original_type == "thick_sketch")
    thin = sum(1 for r in results if r.original_type == "thin_sketch")
    normal = sum(1 for r in results if r.original_type == "normal_sketch")
    errors = sum(1 for r in results if r.original_type == "error")
    
    converted = sum(1 for r in results if r.action == "photo_to_sketch")
    thinned = sum(1 for r in results if r.action == "thinned")
    thickened = sum(1 for r in results if r.action == "thickened")
    kept = sum(1 for r in results if r.action == "kept")
    deleted = sum(1 for r in results if r.action == "deleted")
    
    # 통계 출력
    print(f"총 이미지: {total}개")
    print(f"\n원본 분류:")
    print(f"  📸 실물 사진: {photos}개")
    print(f"  📐 스케치/도면: {sketches}개")
    print(f"    ├─ 📏 굵은 스케치: {thick}개")
    print(f"    ├─ ✏️  얇은 스케치: {thin}개")
    print(f"    └─ ✅ 적절한 스케치: {normal}개")
    print(f"\n처리 결과:")
    print(f"  🎨 사진→스케치 변환: {converted}개")
    print(f"  📉 선 세밀화: {thinned}개")
    print(f"  📈 선 굵기 보강: {thickened}개")
    print(f"  ⏸️  유지됨: {kept}개")
    if delete_photos:
        print(f"  🗑️  원본 삭제됨: {deleted}개")
    print(f"  ❌ 오류: {errors}개")
    print(f"{'='*80}\n")
    
    return results


def save_process_log(results: List[ProcessResult], input_dir: str, 
                     target_thickness: float, delete_photos: bool):
    """
    처리 로그를 JSON 파일로 저장
    
    저장 내용:
    - 버전 정보
    - 처리 시간
    - 설정값 (목표 굵기, 삭제 옵션)
    - 통계
    - 각 파일별 상세 결과
    """
    log_path = os.path.join(input_dir, "process_log.json")
    
    # 로그 데이터 구성
    log_data = {
        "version": "4.0-final",  # 코드 버전
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),  # 처리 시간
        "directory": input_dir,  # 입력 디렉토리
        "target_thickness": target_thickness,  # 목표 선 굵기
        "delete_photos": delete_photos,  # 삭제 옵션
        "backup_directory": os.path.join(input_dir, "backup_original"),
        "output_directory": os.path.join(input_dir, "processed_sketches"),
        "total": len(results),  # 총 파일 수
        "statistics": {
            # 통계 정보
            "photos": sum(1 for r in results if r.original_classification == "photo"),
            "sketches": sum(1 for r in results if r.original_classification == "sketch"),
            "thick_sketches": sum(1 for r in results if r.original_type == "thick_sketch"),
            "thin_sketches": sum(1 for r in results if r.original_type == "thin_sketch"),
            "normal_sketches": sum(1 for r in results if r.original_type == "normal_sketch"),
            "converted": sum(1 for r in results if r.action == "photo_to_sketch"),
            "thinned": sum(1 for r in results if r.action == "thinned"),
            "thickened": sum(1 for r in results if r.action == "thickened"),
            "kept": sum(1 for r in results if r.action == "kept"),
            "deleted": sum(1 for r in results if r.action == "deleted"),
            "errors": sum(1 for r in results if r.original_type == "error")
        },
        "details": [
            # 각 파일별 상세 정보
            {
                "filename": r.filename,
                "original_classification": r.original_classification,
                "original_type": r.original_type,
                "action": r.action,
                "final_score": round(r.final_score, 4),
                "confidence": round(r.confidence, 4),
                "thickness_before": round(r.avg_line_thickness_before, 2),
                "thickness_after": round(r.avg_line_thickness_after, 2),
                "size_kb": round(r.size_bytes / 1024, 2),
                "backup": r.backup_path,
                "output": r.output_path,
                "error": r.error
            }
            for r in results
        ]
    }
    
    # JSON 파일로 저장 (UTF-8, 들여쓰기 2칸)
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)
    
    print(f"📄 처리 로그 저장: {log_path}\n")


def main():
    """
    메인 함수 - 명령줄 인터페이스
    
    사용법:
        python Photo_sketch_v2.py <폴더경로> [--force] [--target-thickness N] [--delete-photos]
    """
    # 인자가 없으면 도움말 출력
    if len(sys.argv) < 2:
        print("="*80)
        print("🎨 배치 이미지 처리기 - 최종 통합 버전 (V4 Final)")
        print("="*80)
        print("\n사용법:")
        print("  python Photo_sketch_v4_final.py <폴더경로> [옵션]")
        print("\n옵션:")
        print("  --force                확인 없이 즉시 처리")
        print("  --target-thickness N   목표 선 굵기 (기본값: 3 픽셀)")
        print("  --delete-photos        사진 원본 삭제 (스케치 변환 후)")
        print("\n예시:")
        print("  python Photo_sketch_v4_final.py ./images")
        print("  python Photo_sketch_v4_final.py ./images --target-thickness 2.5")
        print("  python Photo_sketch_v4_final.py ./images --force --delete-photos")
        print("  python Photo_sketch_v4_final.py ./images --target-thickness 3 --delete-photos")
        print("\n기능:")
        print("  ✅ 정교한 사진/스케치 분류 (채도, 그라데이션, 엔트로피 분석)")
        print("  ✅ 사진 → 스케치 자동 변환 (Canny 엣지 검출)")
        print("  ✅ 선 굵기 자동 감지 및 조정")
        print("  ✅ 굵은 선 세밀화 / 얇은 선 보강")
        print("  ✅ 원본 자동 백업")
        print("  ✅ 상세 처리 로그 생성")
        print("="*80)
        sys.exit(1)
    
    # 명령줄 인자 파싱
    input_dir = sys.argv[1]  # 첫 번째 인자: 입력 디렉토리
    force = "--force" in sys.argv  # --force 옵션 확인
    delete_photos = "--delete-photos" in sys.argv  # --delete-photos 옵션 확인
    
    # target_thickness 파싱
    target_thickness = 3.0  # 기본값
    for i, arg in enumerate(sys.argv):
        if arg == "--target-thickness" and i + 1 < len(sys.argv):
            try:
                target_thickness = float(sys.argv[i + 1])  # 다음 인자를 float로 변환
            except ValueError:
                print(f"⚠️  경고: 잘못된 --target-thickness 값. 기본값 3.0 사용.")
    
    # 배치 처리 실행
    results = process_batch(input_dir, target_thickness, delete_photos, force)
    
    # 처리 로그 저장
    if results:
        save_process_log(results, input_dir, target_thickness, delete_photos)


# 스크립트 직접 실행 시
if __name__ == "__main__":
    main()
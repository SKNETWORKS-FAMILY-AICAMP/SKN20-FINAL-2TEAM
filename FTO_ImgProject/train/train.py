"""
CLIP Fine-tuning with Contrastive Learning (InfoNCE Loss)
---------------------------------------------------------
[실행 환경 설명]
- 외부 API 없음: 완전 로컬 실행
- CLIP 모델 weights는 최초 1회 OpenAI 서버에서 자동 다운로드 후 캐시
- 이후 학습 연산은 100% 로컬 MPS(Mac GPU) / CUDA / CPU에서 수행

데이터 구조:
- images_reject/      : anchor 이미지 폴더 (원본 또는 전처리 v1)
- images_reject_v2/   : positive 이미지 폴더 (전처리 v2 / 증강)
- dataset_combined_final.xlsx    : cross-folder 페어 (anchor←reject, positive←reject_v2)
- dataset_images_reject.xlsx     : same-folder 내 유사 제품 페어
- dataset_images_reject_v2.xlsx  : same-folder v2 내 유사 제품 페어

학습 전략:
- 3개 엑셀을 통합하여 하나의 페어 데이터셋 구성
- CLIP ViT-B/32 백본 파인튜닝
- InfoNCE(NT-Xent) Contrastive Loss
- In-batch negatives 활용
"""

# ────────────────────────────────────────────────
# [Import]
# ────────────────────────────────────────────────

import os                          # 파일/폴더 경로 처리 (os.path.join, os.makedirs 등)
import random                      # Python 기본 난수 → 시드 고정으로 재현성 보장
import logging                     # 학습 로그를 파일 + 콘솔에 동시 출력
import argparse                    # 터미널에서 --epochs 같은 인자를 받기 위한 파서
from pathlib import Path           # 경로를 객체로 다루는 모듈 (glob으로 이미지 탐색 등)

import numpy as np                 # 배열 연산 + cos annealing 수식(np.cos, np.pi)에 사용
import pandas as pd                # 엑셀 파일 로딩(read_excel) + 히스토리 저장(to_csv)
from PIL import Image              # 이미지 파일 열기 + RGB 변환 (CLIP 입력 형식 맞춤)

import torch                       # PyTorch 핵심: 텐서 연산, 모델 저장/로드
import torch.nn as nn              # nn.Module 상속용 (InfoNCELoss 클래스 정의에 필요)
import torch.nn.functional as F    # F.normalize(L2 정규화), F.cross_entropy(loss 계산)
from torch.utils.data import Dataset, DataLoader  # 커스텀 데이터셋 클래스 + 배치 로더
from torch.amp import GradScaler, autocast         # FP16 혼합정밀도 학습 (CUDA 전용)

import clip                        # OpenAI CLIP 라이브러리 (로컬 실행, 외부 API 아님)
# clip.load()시 최초 1회만 서버에서 weights 다운로드
from tqdm import tqdm              # 터미널 진행률 게이지 (epoch/step 막대 표시)
from sklearn.model_selection import train_test_split  # train/val 셋 랜덤 분리


# ────────────────────────────────────────────────
# 0. Config
# ────────────────────────────────────────────────

def get_config():
    # 터미널 인자 파서 생성
    parser = argparse.ArgumentParser(description="CLIP Contrastive Fine-tuning")

    # ── 경로 설정 ──
    parser.add_argument("--anchor_dir", type=str,
                        default="/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/평가데이터/images_reject",
                        help="anchor 이미지 폴더 경로")           # 실제 이미지가 있는 폴더
    parser.add_argument("--positive_dir", type=str,
                        default="/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/평가데이터/images_reject_v2",
                        help="positive 이미지 폴더 경로 (증강/전처리 v2)")  # 증강된 버전 폴더
    parser.add_argument("--data_combined", type=str,
                        default="/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/평가데이터/dataset_combined_final.xlsx")
    parser.add_argument("--data_reject", type=str,
                        default="/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/평가데이터/dataset_images_reject.xlsx")
    parser.add_argument("--data_reject_v2", type=str,
                        default="/Users/kangminji/__SKN20_FINAL/데이터셋만들기/3차_테스트/평가데이터/dataset_images_reject_v2.xlsx")
    parser.add_argument("--output_dir", type=str,
                        default="/Users/kangminji/__SKN20_FINAL/데이터셋만들기/train/checkpoints")  # 모델 저장 위치

    # ── 학습 하이퍼파라미터 ──
    parser.add_argument("--clip_model", type=str, default="ViT-B/32",
                        choices=["ViT-B/32", "ViT-B/16", "ViT-L/14"],
                        help="CLIP 백본 모델")                    # B/32가 가장 가볍고 빠름
    parser.add_argument("--epochs", type=int, default=100)         # 총 학습 반복 횟수
    parser.add_argument("--batch_size", type=int, default=8,
                        help="배치 크기 (In-batch negatives 수 = batch_size - 1) | Mac 권장: 8")
    parser.add_argument("--lr", type=float, default=1e-5,
                        help="Learning rate (CLIP은 낮은 LR 권장)")  # 너무 높으면 pretrain 망각
    parser.add_argument("--weight_decay", type=float, default=1e-4)  # AdamW L2 정규화 계수
    parser.add_argument("--temperature", type=float, default=0.07,
                        help="InfoNCE temperature (낮을수록 hard negative 강조)")  # 0.07은 CLIP 원논문 값
    parser.add_argument("--val_ratio", type=float, default=0.15,   # 전체 데이터의 15%를 검증셋으로
                        help="Validation 비율")
    parser.add_argument("--seed", type=int, default=42)             # 재현성을 위한 랜덤 시드
    parser.add_argument("--num_workers", type=int, default=4)       # DataLoader 병렬 로딩 프로세스 수
                                                                    # Mac에서 느리면 0으로 변경
    parser.add_argument("--freeze_text", action="store_true", default=True,
                        help="텍스트 인코더 freeze (이미지 검색 특화)")  # 이미지만 쓰므로 텍스트는 동결
    parser.add_argument("--unfreeze_layers", type=int, default=2,
                        help="CLIP 비주얼 인코더 상위 N개 레이어만 fine-tune")  # 2 = 마지막 2블록만 학습

    return parser.parse_args()  # 파싱된 인자를 Namespace 객체로 반환


# ────────────────────────────────────────────────
# 1. 데이터 로딩 & 병합
# ────────────────────────────────────────────────

def load_all_pairs(cfg) -> pd.DataFrame:
    """
    3개의 엑셀을 통합하여 통일된 컬럼 구조로 반환.

    반환 컬럼:
    anchor_path  : 실제 파일 경로 (str)
    positive_path: 실제 파일 경로 (str)
    source       : 어느 엑셀 출처인지 (디버깅용)
    """
    rows = []  # 모든 페어를 담을 리스트 (나중에 DataFrame으로 변환)

    # ── (1) dataset_combined_final: anchor=reject폴더, positive=reject_v2폴더 ──
    df_combined = pd.read_excel(cfg.data_combined)          # 엑셀 로드
    for _, row in df_combined.iterrows():                   # 행 단위로 순회
        anchor_path   = os.path.join(cfg.anchor_dir,   row.iloc[0])   # 폴더 + 파일명 조합
        positive_path = os.path.join(cfg.positive_dir, row.iloc[1])   # v2 폴더 + 파일명 조합
        rows.append({
            "anchor_path":   anchor_path,
            "positive_path": positive_path,
            "source": "combined"   # 출처 표시 (디버깅/분석용)
        })

    # ── (2) dataset_images_reject: 같은 reject 폴더 내 유사 제품 페어 ──
    df_reject = pd.read_excel(cfg.data_reject)
    for _, row in df_reject.iterrows():
        anchor_path   = os.path.join(cfg.anchor_dir, row["anchor"])    # 컬럼명으로 접근
        positive_path = os.path.join(cfg.anchor_dir, row["positive"])  # 같은 폴더 내 다른 이미지
        rows.append({
            "anchor_path":   anchor_path,
            "positive_path": positive_path,
            "source": "reject"
        })

    # ── (3) dataset_images_reject_v2: 같은 reject_v2 폴더 내 유사 제품 페어 ──
    df_reject_v2 = pd.read_excel(cfg.data_reject_v2)
    for _, row in df_reject_v2.iterrows():
        anchor_path   = os.path.join(cfg.positive_dir, row["anchor"])   # v2 폴더 기준
        positive_path = os.path.join(cfg.positive_dir, row["positive"])
        rows.append({
            "anchor_path":   anchor_path,
            "positive_path": positive_path,
            "source": "reject_v2"
        })

    # 리스트 → DataFrame 변환 후 완전히 같은 페어 중복 제거
    df = pd.DataFrame(rows).drop_duplicates(subset=["anchor_path", "positive_path"])

    # 파일 존재 여부 검증 (경로는 있지만 실제 파일 없는 경우 제거)
    before = len(df)
    df = df[
        df["anchor_path"].apply(os.path.exists) &    # anchor 파일 실제 존재 확인
        df["positive_path"].apply(os.path.exists)    # positive 파일 실제 존재 확인
    ].reset_index(drop=True)                         # 인덱스 재정렬
    missing = before - len(df)                       # 제거된 페어 수 계산
    if missing > 0:
        logging.warning(f"⚠️  파일 없음으로 제외된 페어: {missing}개")

    logging.info(f"✅ 총 유효 페어: {len(df)}개 "
                f"(combined={sum(df.source=='combined')}, "
                f"reject={sum(df.source=='reject')}, "
                f"reject_v2={sum(df.source=='reject_v2')})")
    return df


# ────────────────────────────────────────────────
# 2. Dataset
# ────────────────────────────────────────────────

class PairDataset(Dataset):
    """
    anchor, positive 이미지 페어를 반환하는 Dataset.
    데이터가 적으므로 메모리 캐싱 옵션 포함.
    """

    def __init__(self, df: pd.DataFrame, preprocess, augment=False, cache=True):
        self.df         = df.reset_index(drop=True)  # 인덱스 초기화하여 저장
        self.preprocess = preprocess                  # CLIP 전처리 함수 (resize, normalize)
        self.augment    = augment                     # 학습셋만 True (현재는 예약 옵션)
        self.cache      = cache                       # True면 이미지를 메모리에 저장 (재사용 빠름)
        self._img_cache = {}                          # 캐시 딕셔너리 {경로: PIL Image}

    def _load(self, path: str) -> Image.Image:
        if self.cache:
            if path not in self._img_cache:                          # 처음 로드하는 경우만
                self._img_cache[path] = Image.open(path).convert("RGB")  # RGB로 통일 저장
            return self._img_cache[path].copy()                      # 캐시된 이미지 복사본 반환
                                                                    # (copy 안 하면 augment시 원본 변형됨)
        return Image.open(path).convert("RGB")                       # 캐시 미사용시 매번 새로 로드

    def __len__(self):
        return len(self.df)   # DataLoader가 배치 수 계산에 사용

    def __getitem__(self, idx):
        row = self.df.iloc[idx]                           # idx번째 페어 행 가져오기
        anchor_img   = self._load(row["anchor_path"])     # anchor 이미지 로드
        positive_img = self._load(row["positive_path"])   # positive 이미지 로드

        anchor_tensor   = self.preprocess(anchor_img)     # CLIP 전처리: 224×224 리사이즈 + 정규화
        positive_tensor = self.preprocess(positive_img)   # 동일하게 전처리

        return anchor_tensor, positive_tensor             # 텐서 페어 반환


# ────────────────────────────────────────────────
# 3. Model 설정 (Partial Freeze)
# ────────────────────────────────────────────────

def build_model(cfg, device):
    """
    CLIP 모델 로드 후 freeze 전략 적용.

    전략:
    - 텍스트 인코더: 완전 freeze (이미지 검색 태스크이므로 불필요)
    - 비주얼 인코더: 상위 unfreeze_layers개 트랜스포머 블록만 학습
    - logit_scale: 학습 가능 유지
    """
    model, preprocess = clip.load(cfg.clip_model, device=device)
    # clip.load: 최초 실행시 OpenAI 서버에서 ViT-B/32 weights 다운로드 (~340MB)
    # 이후는 로컬 캐시(~/.cache/clip/)에서 즉시 로드
    # preprocess: CLIP 전용 이미지 전처리 함수 반환 (resize 224, center crop, normalize)

    model = model.float()  # CLIP은 기본 float16 → float32로 변환 (MPS/CPU 안정성 확보)

    # 모든 파라미터 학습 비활성화 (전체 freeze)
    for param in model.parameters():
        param.requires_grad = False  # gradient 계산 차단 → 메모리/속도 절약

    # 텍스트 인코더 unfreeze 옵션 (이미지 검색이므로 기본값 True = 동결 유지)
    if not cfg.freeze_text:
        for param in model.transformer.parameters():
            param.requires_grad = True   # 텍스트 인코더 학습 활성화 (이 코드에선 사용 안 함)

    # 비주얼 인코더 트랜스포머 블록 목록 가져오기
    visual_blocks = model.visual.transformer.resblocks   # ViT-B/32는 총 12개 블록
    total_blocks  = len(visual_blocks)                   # 12
    unfreeze_from = total_blocks - cfg.unfreeze_layers   # 12 - 2 = 10 → 10번째 이후 unfreeze

    for i, block in enumerate(visual_blocks):
        if i >= unfreeze_from:                      # 10, 11번 블록만 (마지막 2개)
            for param in block.parameters():
                param.requires_grad = True          # 이 블록만 gradient 계산 활성화

    # Visual projection 레이어 unfreeze (이미지 → 임베딩 공간 투영 행렬)
    for param in model.visual.proj.parameters() if hasattr(model.visual.proj, 'parameters') else []:
        param.requires_grad = True   # proj는 일반적으로 텐서라 parameters()가 없을 수 있음

    # LayerNorm (마지막 정규화 레이어) unfreeze
    if hasattr(model.visual, 'ln_post'):
        for param in model.visual.ln_post.parameters():
            param.requires_grad = True   # 출력 직전 정규화 레이어도 학습

    # logit_scale: CLIP의 temperature 파라미터 (학습 가능하게 유지)
    model.logit_scale.requires_grad = True   # log(1/temperature) 값, 자동 조정됨

    # 학습 파라미터 통계 출력
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)   # 학습 파라미터 수
    total     = sum(p.numel() for p in model.parameters())                       # 전체 파라미터 수
    logging.info(f"학습 파라미터: {trainable:,} / {total:,} "
                f"({100*trainable/total:.1f}%)")  # 실행 결과: 14,177,281 / 151,277,313 (9.4%)

    return model, preprocess


# ────────────────────────────────────────────────
# 4. Loss: InfoNCE (NT-Xent, Symmetric)
# ────────────────────────────────────────────────

class InfoNCELoss(nn.Module):
    """
    Symmetric InfoNCE Loss.

    배치 내 다른 샘플들이 자동으로 negative 역할을 함.
    배치 크기가 클수록 hard negative가 많아져 학습 효과 ↑

    Args:
        temperature: 낮을수록 negative 구별을 엄격하게 학습
    """

    def __init__(self, temperature: float = 0.07):
        super().__init__()
        self.temperature = temperature   # 분모에 나눠서 logit 스케일 조정

    def forward(self, anchor_feat: torch.Tensor,
                positive_feat: torch.Tensor) -> torch.Tensor:

        # L2 정규화: 각 임베딩 벡터의 크기를 1로 만들어 코사인 유사도 비교 가능하게 함
        anchor_feat   = F.normalize(anchor_feat,   dim=-1)   # [B, D] → 각 행의 norm = 1
        positive_feat = F.normalize(positive_feat, dim=-1)   # [B, D]

        # 유사도 행렬 계산: anchor[i]와 positive[j] 간의 코사인 유사도
        # [B, D] × [D, B] = [B, B] → (i, j) 원소 = anchor_i와 positive_j의 유사도
        logits = torch.matmul(anchor_feat, positive_feat.T) / self.temperature
        # temperature로 나누면 낮을수록 대각선(정답)과 비대각선(오답)의 차이가 커짐

        # 정답 레이블: 대각선 위치 (i번째 anchor의 정답은 i번째 positive)
        labels = torch.arange(len(logits), device=logits.device)  # [0, 1, 2, ..., B-1]

        # Symmetric Loss: 양방향으로 모두 학습
        loss_a2p = F.cross_entropy(logits,   labels)   # anchor → positive 방향
        loss_p2a = F.cross_entropy(logits.T, labels)   # positive → anchor 방향

        return (loss_a2p + loss_p2a) / 2   # 두 방향의 평균 반환


# ────────────────────────────────────────────────
# 5. Evaluation: Recall@K
# ────────────────────────────────────────────────

@torch.no_grad()   # 평가 시 gradient 계산 불필요 → 메모리/속도 절약
def evaluate_recall_at_k(model, val_loader, device, k_list=(1, 5, 10)):
    """
    Image Retrieval 평가 지표: Recall@K

    방식:
    - 전체 val 셋의 anchor/positive 임베딩 추출
    - anchor 기준으로 가장 유사한 K개 중 정답(positive)이 있는지 확인
    """
    model.eval()           # BatchNorm/Dropout 등을 평가 모드로 전환
    anchors_list   = []    # 배치별 anchor 임베딩 수집용
    positives_list = []    # 배치별 positive 임베딩 수집용

    for anchor_imgs, positive_imgs in val_loader:
        anchor_feats   = model.encode_image(anchor_imgs.to(device))    # 이미지 → 임베딩 벡터
        positive_feats = model.encode_image(positive_imgs.to(device))  # 동일하게 추출
        anchors_list.append(F.normalize(anchor_feats.float(), dim=-1).cpu())    # L2 정규화 후 CPU로
        positives_list.append(F.normalize(positive_feats.float(), dim=-1).cpu())

    anchors   = torch.cat(anchors_list)    # 배치 리스트를 하나로 합침 [N, D]
    positives = torch.cat(positives_list)  # [N, D]

    # 전체 anchor vs 전체 positive 코사인 유사도 행렬
    sim_matrix = torch.matmul(anchors, positives.T)   # [N, N]
    # (i, i) 대각선 = 정답 쌍의 유사도, 나머지는 다른 샘플과의 유사도

    recalls = {}
    for k in k_list:
        k_eff = min(k, len(anchors))                              # K가 샘플 수보다 크면 조정
        top_k_indices = sim_matrix.topk(k_eff, dim=1).indices    # 각 anchor의 top-K positive 인덱스 [N, K]
        labels        = torch.arange(len(anchors))               # 정답 인덱스 [0, 1, ..., N-1]
        correct       = (top_k_indices == labels.unsqueeze(1)).any(dim=1)  # top-K 안에 정답 있으면 True
        recalls[f"R@{k}"] = correct.float().mean().item()        # True 비율 = Recall@K

    return recalls   # {'R@1': 0.4286, 'R@5': 1.0, 'R@10': 1.0} 형태


# ────────────────────────────────────────────────
# 6. Training Loop
# ────────────────────────────────────────────────

def train_one_epoch(model, loader, optimizer, criterion,
                    scaler, device, epoch, cfg):
    model.train()     # BatchNorm/Dropout 학습 모드로 전환 (현재 CLIP에선 큰 차이 없으나 관례)
    total_loss = 0.0  # epoch 전체 loss 누적용

    # tqdm으로 step 진행률 표시 (leave=False: epoch 끝나면 줄 삭제)
    for step, (anchor_imgs, positive_imgs) in enumerate(tqdm(loader, desc=f"Epoch {epoch}", leave=False)):
        anchor_imgs   = anchor_imgs.to(device)    # 텐서를 MPS/CUDA/CPU로 이동
        positive_imgs = positive_imgs.to(device)

        optimizer.zero_grad()   # 이전 step의 gradient 초기화 (누적 방지)

        # CUDA일 때만 FP16 혼합정밀도 사용 (MPS는 autocast 미지원)
        with autocast("cuda", enabled=(device.type == "cuda")):
            anchor_feats   = model.encode_image(anchor_imgs)    # 이미지 → 임베딩 [B, 512]
            positive_feats = model.encode_image(positive_imgs)  # 동일하게 추출
            loss = criterion(anchor_feats.float(), positive_feats.float())  # InfoNCE loss 계산

        if device.type == "cuda":
            # CUDA: FP16 gradient 스케일링으로 underflow 방지
            scaler.scale(loss).backward()       # loss에 scale 곱한 뒤 backward
            scaler.unscale_(optimizer)          # gradient를 원래 스케일로 복원
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1.0)  # gradient 폭발 방지 (최대 norm=1)
            scaler.step(optimizer)              # optimizer로 파라미터 업데이트
            scaler.update()                     # 다음 step을 위한 scaler 갱신
        else:
            # Mac MPS / CPU: autocast 미지원이므로 일반 backward
            loss.backward()                     # gradient 계산
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1.0)  # gradient 클리핑
            optimizer.step()                    # 파라미터 업데이트

        total_loss += loss.item()   # 텐서 → Python float으로 변환 후 누적

        # 10 step마다 로그 출력 (너무 자주 출력하면 느려짐)
        if (step + 1) % 10 == 0:
            logging.info(f"  Epoch {epoch} | Step {step+1}/{len(loader)} "
                        f"| Loss: {loss.item():.4f}")

    return total_loss / len(loader)   # epoch 평균 loss 반환


# ────────────────────────────────────────────────
# 7. Main
# ────────────────────────────────────────────────

def main():
    cfg = get_config()   # 터미널 인자 파싱 (없으면 default 값 사용)

    # 로깅 설정: 파일과 콘솔에 동시 출력
    os.makedirs(cfg.output_dir, exist_ok=True)   # 체크포인트 폴더 없으면 생성
    logging.basicConfig(
        level=logging.INFO,                       # INFO 이상 레벨만 출력
        format="%(asctime)s [%(levelname)s] %(message)s",   # 시간 + 레벨 + 메시지
        handlers=[
            logging.FileHandler(os.path.join(cfg.output_dir, "train.log")),  # 파일 저장
            logging.StreamHandler()               # 터미널 출력
        ]
    )

    # 재현성을 위한 시드 고정 (같은 시드면 매번 같은 결과)
    random.seed(cfg.seed)      # Python random 시드
    np.random.seed(cfg.seed)   # NumPy 시드
    torch.manual_seed(cfg.seed)  # PyTorch 시드

    # 사용 가능한 디바이스 자동 감지 (우선순위: CUDA > MPS > CPU)
    device = torch.device(
        "cuda"  if torch.cuda.is_available() else        # NVIDIA GPU
        "mps"   if torch.backends.mps.is_available() else  # Mac Apple Silicon GPU
        "cpu"                                            # 폴백
    )
    logging.info(f"Device: {device}")   # 실행 결과: Device: mps

    # ── 데이터 로드 ──
    df_all = load_all_pairs(cfg)   # 3개 엑셀 통합 → 유효 페어 DataFrame

    # 전체 데이터를 train/val로 분리 (val_ratio=0.15 → 85%/15%)
    train_df, val_df = train_test_split(
        df_all, test_size=cfg.val_ratio,
        random_state=cfg.seed,   # 시드 고정으로 매번 같은 분할
        shuffle=True             # 분할 전 셔플
    )
    logging.info(f"Train: {len(train_df)}쌍 | Val: {len(val_df)}쌍")

    # ── 모델 ──
    model, preprocess = build_model(cfg, device)   # CLIP 로드 + freeze 전략 적용

    # ── Dataset / DataLoader ──
    train_dataset = PairDataset(train_df, preprocess, augment=True,  cache=True)  # 학습셋
    val_dataset   = PairDataset(val_df,   preprocess, augment=False, cache=True)  # 검증셋

    train_loader = DataLoader(
        train_dataset, batch_size=cfg.batch_size,
        shuffle=True,                              # 매 epoch마다 순서 섞기
        num_workers=cfg.num_workers,               # 병렬 로딩 프로세스 수 (Mac: 0 권장)
        pin_memory=(device.type == "cuda"),        # CUDA만 pin_memory 사용 (MPS는 에러남)
        drop_last=True                             # 마지막 배치가 batch_size 미만이면 버림
                                                    # (InfoNCE는 배치 크기 균일해야 함)
    )
    val_loader = DataLoader(
        val_dataset, batch_size=cfg.batch_size,
        shuffle=False,                             # 검증셋은 순서 고정
        num_workers=cfg.num_workers,
        pin_memory=(device.type == "cuda")
    )

    # ── Loss / Optimizer / Scheduler ──
    criterion = InfoNCELoss(temperature=cfg.temperature)   # temperature=0.07로 초기화

    trainable_params = [p for p in model.parameters() if p.requires_grad]   # 학습할 파라미터만
    optimizer = torch.optim.AdamW(
        trainable_params, lr=cfg.lr, weight_decay=cfg.weight_decay
        # AdamW: Adam + weight decay 분리 (L2 정규화보다 안정적)
    )

    # Cosine Annealing with Warmup (수동 구현)
    total_steps  = cfg.epochs * len(train_loader)          # 전체 step 수 (100 × 29 = 2900)
    warmup_steps = int(0.1 * total_steps)                  # 초반 10% step은 LR을 서서히 올림 (290 steps)

    def lr_lambda(step):
        if step < warmup_steps:
            return step / max(1, warmup_steps)             # 0 → 1로 선형 증가 (warmup)
        progress = (step - warmup_steps) / max(1, total_steps - warmup_steps)
        return 0.5 * (1.0 + np.cos(np.pi * progress))     # 1 → 0으로 코사인 감소

    # LambdaLR: lr_lambda 함수로 step마다 lr 계수를 계산
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)

    # GradScaler: CUDA FP16 학습시 gradient underflow 방지 (MPS는 enabled=False)
    scaler = GradScaler("cuda", enabled=(device.type == "cuda"))

    # ── 학습 ──
    best_recall = 0.0   # 최고 R@1 기록 (best 모델 저장 기준)
    history = []        # epoch별 loss/recall 기록 (나중에 CSV로 저장)

    # epoch 전체 진행률 게이지 (우측에 loss, R@1, best 실시간 표시)
    epoch_bar = tqdm(range(1, cfg.epochs + 1), desc="Training", unit="epoch")

    for epoch in epoch_bar:
        # 1 epoch 학습 실행 → 평균 loss 반환
        train_loss = train_one_epoch(
            model, train_loader, optimizer, criterion,
            scaler, device, epoch, cfg
        )
        scheduler.step()   # step 기반 LR 스케줄러 업데이트

        # 검증셋으로 Recall@K 계산
        recalls = evaluate_recall_at_k(model, val_loader, device)
        r1 = recalls.get("R@1", 0.0)   # 핵심 지표

        # tqdm 게이지 우측에 현재 상태 표시
        epoch_bar.set_postfix({
            "loss": f"{train_loss:.4f}",
            "R@1":  f"{r1:.4f}",
            "best": f"{best_recall:.4f}"
        })

        # 로그 파일 + 콘솔에 epoch 결과 출력
        logging.info(
            f"Epoch {epoch}/{cfg.epochs} | "
            f"Train Loss: {train_loss:.4f} | "
            + " | ".join(f"{k}: {v:.4f}" for k, v in recalls.items())
        )

        history.append({"epoch": epoch, "train_loss": train_loss, **recalls})   # 기록 저장

        # R@1이 이전 최고보다 높으면 모델 저장
        if r1 > best_recall:
            best_recall = r1
            ckpt_path = os.path.join(cfg.output_dir, "best_model.pt")
            torch.save({
                "epoch":       epoch,              # 저장된 epoch 번호
                "model_state": model.state_dict(), # 모델 가중치
                "optimizer":   optimizer.state_dict(),  # optimizer 상태 (재학습시 필요)
                "recalls":     recalls,            # 저장 당시 recall 지표
                "config":      vars(cfg),          # 학습에 사용한 하이퍼파라미터 전체
            }, ckpt_path)
            logging.info(f"  ✅ Best model saved (R@1={r1:.4f})")

    # 학습 히스토리를 CSV로 저장 (epoch별 loss + recall 추이 분석용)
    pd.DataFrame(history).to_csv(
        os.path.join(cfg.output_dir, "train_history.csv"), index=False)
    logging.info("학습 완료!")
    
    # ── 학습 결과 요약 출력 ──
    best_row   = history.loc[history["R@1"].idxmax()]   # R@1 최고 epoch 행
    final_row  = history.iloc[-1]                          # 마지막 epoch 행

    summary = f"""
╔══════════════════════════════════════════════╗
║              📊 학습 결과 요약                   ║
╠══════════════════════════════════════════════╣
║  총 Epoch       : {cfg.epochs:<5}                       ║
║  소요 시간      : {cfg.epochs * 54 // 60}분 {cfg.epochs * 54 % 60}초 (약)               ║
╠══════════════════════════════════════════════╣
║  [Best Model - Epoch {int(best_row['epoch']):<3}]                   ║
║    R@1  : {best_row['R@1']:.4f}                          ║
║    R@5  : {best_row['R@5']:.4f}                          ║
║    R@10 : {best_row['R@10']:.4f}                          ║
║    Loss : {best_row['train_loss']:.4f}                          ║
╠══════════════════════════════════════════════╣
║  [Final Epoch {int(final_row['epoch']):<3}]                        ║
║    R@1  : {final_row['R@1']:.4f}                          ║
║    R@5  : {final_row['R@5']:.4f}                          ║
║    R@10 : {final_row['R@10']:.4f}                          ║
║    Loss : {final_row['train_loss']:.4f}                          ║
╠══════════════════════════════════════════════╣
║  저장 경로: {os.path.basename(cfg.output_dir):<35} ║
╚══════════════════════════════════════════════╝
"""
    print(summary)
    logging.info("학습 완료!")



if __name__ == "__main__":
    main()   # 이 파일을 직접 실행할 때만 main() 호출 (import시에는 실행 안 됨)
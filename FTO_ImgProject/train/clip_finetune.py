"""
CLIP ViT-B/32 Fine-tuning with Triplet Loss
=============================================
triplets.csv  →  CLIP 파인튜닝  →  저장된 모델 (clip_finetuned.pt)

데이터 구조:
anchor_path   : 기준 이미지 (로컬 경로)
positive_path : 같은 출원번호의 다른 도면  (유사 = 가까워야 함)
negative_path : 다른 출원번호 이미지      (비유사 = 멀어야 함)
negative_type : 'hard'(같은 물품명) / 'easy'(다른 물품명)

학습 전략:
- Triplet Margin Loss (margin=0.2)
- hard negative를 더 많이 샘플링 (어려운 것 먼저 학습)
- CLIP Visual Encoder만 파인튜닝 (Text Encoder 동결)
- 마지막 4개 Transformer Block만 업데이트 (앞단 동결)
- ReduceLROnPlateau로 학습률 자동 조정
전략: CLIP Visual Encoder 마지막 4 Transformer Block만 업데이트
    → 앞단 동결으로 기존 CLIP 표현력 보존
    → 과적합 방지

Loss: Triplet Margin Loss (margin=0.2)
    d(anchor, positive) + 0.2 < d(anchor, negative) 가 되도록 학습

모니터링 지표:
d_pos = anchor ↔ positive 거리  (내려가야 함)
d_neg = anchor ↔ negative 거리  (올라가야 함)
gap   = d_neg - d_pos            (커질수록 성공)


# 1. 의존성 설치
pip install ftfy regex tqdm

# 2. 학습 시작
python clip_finetune.py

# 3. 결과 확인
# clip_finetuned/clip_finetuned_best.pt  ← 최적 모델
# clip_finetuned/training_log.csv        ← 에폭별 loss/gap 추이
"""

import os
import csv
import random
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from PIL import Image
import clip
from datetime import datetime

# ─────────────────────────────────────────────
# 0. 설정
# ─────────────────────────────────────────────
TRIPLET_CSV   = "/Users/kangminji/__SKN20_FINAL/데이터셋만들기/processed/data/triplets.csv" # triplets.csv — 41,792행
# hard negative: 20,318개  ← 같은 화장품용기인데 다른 디자인 → 모델이 세밀하게 학습
# easy negative: 21,474개  ← 아예 다른 물품명 → 기본 분리 학습
OUTPUT_DIR    = "/Users/kangminji/__SKN20_FINAL/데이터셋만들기/train/clip_finetuned"
CLIP_MODEL    = "ViT-B/32"

EPOCHS        = 30
BATCH_SIZE    = 32           # GPU 메모리에 따라 16~64 조정
LR            = 1e-5         # CLIP 파인튜닝은 낮은 학습률 필수
MARGIN        = 0.2          # Triplet margin
HARD_RATIO    = 0.7          # 전체 배치 중 hard negative 비율
VAL_RATIO     = 0.1          # 검증 셋 비율
SEED          = 42

os.makedirs(OUTPUT_DIR, exist_ok=True)
random.seed(SEED)
torch.manual_seed(SEED)

DEVICE = (
    "cuda" if torch.cuda.is_available() else
    "mps"  if torch.backends.mps.is_available() else
    "cpu"
)
print(f"Device: {DEVICE}")


# ─────────────────────────────────────────────
# 1. Dataset
# ─────────────────────────────────────────────
class TripletDesignDataset(Dataset):
    """
    triplets.csv 로드 → (anchor, positive, negative) PIL 이미지 반환

    hard/easy 비율 조정 가능:
      hard_ratio=0.7 → hard 70% + easy 30% 로 샘플링
    """
    def __init__(self, rows: list, preprocess, hard_ratio: float = HARD_RATIO):
        self.preprocess  = preprocess

        hard = [r for r in rows if r["negative_type"] == "hard"]
        easy = [r for r in rows if r["negative_type"] == "easy"]

        n_hard = int(len(rows) * hard_ratio)
        n_easy = len(rows) - n_hard
        n_hard = min(n_hard, len(hard))
        n_easy = min(n_easy, len(easy))

        sampled = random.sample(hard, n_hard) + random.sample(easy, n_easy)
        random.shuffle(sampled)
        self.rows = sampled
        print(f"  Dataset: {len(self.rows):,}개 (hard={n_hard:,}, easy={n_easy:,})")

    def __len__(self):
        return len(self.rows)

    def __getitem__(self, idx):
        row = self.rows[idx]
        anchor   = self._load(row["anchor_path"])
        positive = self._load(row["positive_path"])
        negative = self._load(row["negative_path"])
        return anchor, positive, negative

    def _load(self, path: str) -> torch.Tensor:
        img = Image.open(path).convert("RGB")
        return self.preprocess(img)


# ─────────────────────────────────────────────
# 2. 학습 가능 레이어 설정
#    CLIP Visual Encoder의 마지막 4개 Block만 파인튜닝
#    (앞단 동결 → 기존 표현력 보존 + 과적합 방지)
# ─────────────────────────────────────────────
def freeze_clip_except_last_blocks(model, n_unfreeze: int = 4):
    """
    Visual Encoder(ViT)의 마지막 n_unfreeze개 Transformer Block만 학습.
    Text Encoder와 나머지 Visual 레이어는 완전 동결.
    """
    # 전체 동결
    for param in model.parameters():
        param.requires_grad = False

    # Visual Encoder 마지막 N 블록 해동
    visual_blocks = model.visual.transformer.resblocks
    total_blocks  = len(visual_blocks)
    for i, block in enumerate(visual_blocks):
        if i >= total_blocks - n_unfreeze:
            for param in block.parameters():
                param.requires_grad = True

    # Visual Encoder projection 레이어 해동
    if hasattr(model.visual, 'proj') and model.visual.proj is not None:
        model.visual.proj.requires_grad = True

    # 학습 파라미터 수 출력
    total  = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"  전체 파라미터:   {total:,}")
    print(f"  학습 파라미터:   {trainable:,} ({trainable/total*100:.1f}%)")
    print(f"  동결 파라미터:   {total-trainable:,} ({(total-trainable)/total*100:.1f}%)")
    return model


# ─────────────────────────────────────────────
# 3. Triplet Loss
# ─────────────────────────────────────────────
class TripletLoss(nn.Module):
    """
    L2 정규화된 임베딩에 대한 Triplet Margin Loss.

    loss = max(0, d(a,p) - d(a,n) + margin)

    목표:
      d(anchor, positive) + margin < d(anchor, negative)
      → 같은 출원번호 도면끼리 더 가깝게
      → 다른 출원번호 도면끼리 더 멀게
    """
    def __init__(self, margin: float = MARGIN):
        super().__init__()
        self.margin = margin

    def forward(self, anchor, positive, negative):
        anchor   = F.normalize(anchor,   dim=-1)
        positive = F.normalize(positive, dim=-1)
        negative = F.normalize(negative, dim=-1)

        # 코사인 거리 = 1 - 코사인 유사도
        d_pos = 1.0 - (anchor * positive).sum(dim=-1)   # (B,)
        d_neg = 1.0 - (anchor * negative).sum(dim=-1)   # (B,)

        loss = F.relu(d_pos - d_neg + self.margin)
        return loss.mean(), d_pos.mean().item(), d_neg.mean().item()


# ─────────────────────────────────────────────
# 4. 학습 루프
# ─────────────────────────────────────────────
def encode_batch(model, imgs: torch.Tensor) -> torch.Tensor:
    """이미지 배치 → CLIP visual feature → float32"""
    return model.encode_image(imgs.to(DEVICE)).float()


def run_epoch(model, loader, criterion, optimizer=None, is_train=True):
    model.train(is_train)
    total_loss, total_dp, total_dn, n_batches = 0, 0, 0, 0

    for anchor, positive, negative in loader:
        with torch.set_grad_enabled(is_train):
            a_emb = encode_batch(model, anchor)
            p_emb = encode_batch(model, positive)
            n_emb = encode_batch(model, negative)

            loss, d_pos, d_neg = criterion(a_emb, p_emb, n_emb)

        if is_train and optimizer:
            optimizer.zero_grad()
            loss.backward()
            # Gradient clipping (CLIP 파인튜닝 안정성 향상)
            torch.nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], max_norm=1.0
            )
            optimizer.step()

        total_loss += loss.item()
        total_dp   += d_pos
        total_dn   += d_neg
        n_batches  += 1

    return total_loss/n_batches, total_dp/n_batches, total_dn/n_batches


def main():
    print("=" * 60)
    print("CLIP Fine-tuning with Triplet Loss")
    print("=" * 60)

    # ── CSV 로드 ──
    print("\n[1] CSV 로드 중...")
    with open(TRIPLET_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"  전체 triplet: {len(rows):,}개")

    # ── Train / Val 분할 ──
    random.shuffle(rows)
    n_val   = int(len(rows) * VAL_RATIO)
    val_rows   = rows[:n_val]
    train_rows = rows[n_val:]
    print(f"  Train: {len(train_rows):,}개 / Val: {len(val_rows):,}개")

    # ── CLIP 모델 로드 ──
    print(f"\n[2] CLIP 모델 로드 ({CLIP_MODEL})...")
    model, preprocess = clip.load(CLIP_MODEL, device=DEVICE)
    model = model.float()

    # ── 레이어 동결 설정 ──
    print("\n[3] 레이어 동결 설정 (마지막 4 블록만 학습)...")
    model = freeze_clip_except_last_blocks(model, n_unfreeze=4)

    # ── Dataset / DataLoader ──
    print("\n[4] Dataset 구성...")
    train_ds = TripletDesignDataset(train_rows, preprocess, hard_ratio=HARD_RATIO)
    val_ds   = TripletDesignDataset(val_rows,   preprocess, hard_ratio=0.5)

    train_loader = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True,
                              num_workers=4, pin_memory=True)
    val_loader   = DataLoader(val_ds,   batch_size=BATCH_SIZE, shuffle=False,
                              num_workers=2, pin_memory=True)

    # ── Optimizer & Scheduler ──
    criterion = TripletLoss(margin=MARGIN)
    optimizer = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=LR, weight_decay=1e-4
    )
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="min", factor=0.5, patience=3, verbose=True
    )

    # ── 학습 ──
    print(f"\n[5] 학습 시작 (총 {EPOCHS} 에폭)...")
    best_val_loss = float("inf")
    log_path = os.path.join(OUTPUT_DIR, "training_log.csv")

    with open(log_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["epoch","train_loss","val_loss","d_pos","d_neg","margin_gap","lr"])

    for epoch in range(1, EPOCHS + 1):
        t_loss, t_dp, t_dn = run_epoch(model, train_loader, criterion, optimizer, is_train=True)
        v_loss, v_dp, v_dn = run_epoch(model, val_loader,   criterion, is_train=False)

        scheduler.step(v_loss)
        margin_gap = v_dn - v_dp   # 클수록 좋음 (pos가 neg보다 더 가까움)
        lr_now = optimizer.param_groups[0]["lr"]

        print(
            f"  Epoch {epoch:02d}/{EPOCHS} | "
            f"Train={t_loss:.4f} | Val={v_loss:.4f} | "
            f"d_pos={v_dp:.4f} | d_neg={v_dn:.4f} | "
            f"gap={margin_gap:+.4f} | lr={lr_now:.2e}"
        )

        # 로그 저장
        with open(log_path, "a", newline="") as f:
            csv.writer(f).writerow([epoch, t_loss, v_loss, v_dp, v_dn, margin_gap, lr_now])

        # Best 모델 저장
        if v_loss < best_val_loss:
            best_val_loss = v_loss
            save_path = os.path.join(OUTPUT_DIR, "clip_finetuned_best.pt")
            torch.save({
                "epoch":      epoch,
                "model_state_dict": model.state_dict(),
                "val_loss":   v_loss,
                "margin_gap": margin_gap,
            }, save_path)
            print(f"    ✅ Best 모델 저장: {save_path}")

    # 최종 모델 저장
    final_path = os.path.join(OUTPUT_DIR, "clip_finetuned_final.pt")
    torch.save({"epoch": EPOCHS, "model_state_dict": model.state_dict()}, final_path)
    print(f"\n✅ 최종 모델 저장: {final_path}")
    print(f"📊 학습 로그:      {log_path}")


if __name__ == "__main__":
    main()

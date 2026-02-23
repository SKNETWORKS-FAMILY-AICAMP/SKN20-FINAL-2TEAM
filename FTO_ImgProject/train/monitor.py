"""
학습 진행 상황 실시간 모니터
=============================
python train/monitor.py
"""

import csv
import os
import time
from pathlib import Path
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_PATH     = str(PROJECT_ROOT / "train/checkpoints/training_log.csv")
TOTAL_EPOCHS = 30
POLL_SEC     = 2   # 새 epoch 감지 폴링 주기 (초)


def read_log():
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def format_row(row, is_best):
    ep     = int(row["epoch"])
    t_loss = float(row["train_loss"])
    v_loss = float(row["val_loss"])
    d_pos  = float(row["d_pos"])
    d_neg  = float(row["d_neg"])
    gap    = float(row["margin_gap"])
    lr     = float(row["lr"])
    mark   = " ★ BEST" if is_best else ""
    return (
        f"  {ep:>3} │ {t_loss:.5f} │ {v_loss:.5f} │ "
        f"{d_pos:.4f} │ {d_neg:.4f} │ {gap:+.4f} │ {lr:.0e}{mark}"
    )


def print_summary(rows, pbar):
    done     = len(rows)
    best_idx = min(range(done), key=lambda i: float(rows[i]["val_loss"]))
    latest   = rows[-1]
    best     = rows[best_idx]

    gap_latest = float(latest["margin_gap"])
    gap_best   = float(best["margin_gap"])

    # tqdm postfix 업데이트
    pbar.set_postfix({
        "val_loss": f"{float(latest['val_loss']):.5f}",
        "d_pos":    f"{float(latest['d_pos']):.4f}",
        "d_neg":    f"{float(latest['d_neg']):.4f}",
        "gap":      f"{gap_latest:+.4f}",
        "best_ep":  best["epoch"],
    })
    pbar.update(done - pbar.n)  # 완료된 epoch 수만큼 진행

    # 최신 지표
    print(f"\n  ── Epoch {latest['epoch']}/{TOTAL_EPOCHS} 완료 ──")
    print(f"  train_loss : {float(latest['train_loss']):.5f}")
    print(f"  val_loss   : {float(latest['val_loss']):.5f}")
    print(f"  d_pos      : {float(latest['d_pos']):.4f}  ↓")
    print(f"  d_neg      : {float(latest['d_neg']):.4f}  ↑")
    print(f"  margin_gap : {gap_latest:+.4f}  ↑")
    print(f"  lr         : {float(latest['lr']):.0e}")
    print(f"\n  ★ Best → Epoch {best['epoch']}  val_loss={float(best['val_loss']):.5f}  gap={gap_best:+.4f}")

    # 히스토리 테이블
    print("\n" + "─" * 72)
    print(f"  {'Ep':>3} │ train_l │  val_l  │ d_pos  │ d_neg  │   gap   │   lr")
    print("─" * 72)
    for i, row in enumerate(rows):
        print(format_row(row, is_best=(i == best_idx)))
    print("─" * 72)

    # 프로세스 생존 여부
    alive  = os.popen("ps aux | grep clip_finetune | grep -v grep").read().strip()
    status = "실행 중" if alive else "⚠️  프로세스 없음 — 학습이 중단됐을 수 있습니다"
    print(f"\n  학습 프로세스: {status}")


def main():
    print("=" * 72)
    print("  CLIP ViT-B/32 파인튜닝 — 실시간 모니터  (Ctrl+C 종료)")
    print("=" * 72)

    # 첫 epoch 대기
    rows = read_log()
    if not rows:
        print("\n  ⏳ 첫 번째 epoch 진행 중... (약 2분 소요)")

    while not rows:
        time.sleep(POLL_SEC)
        rows = read_log()

    # tqdm 진행바 초기화
    pbar = tqdm(
        total=TOTAL_EPOCHS,
        desc="  Epochs",
        unit="ep",
        bar_format="{l_bar}{bar:30}{r_bar}",
        dynamic_ncols=True,
    )

    last_done = 0

    try:
        while True:
            rows     = read_log()
            done     = len(rows)

            if done > last_done:
                # 새 epoch 완료 시에만 화면 갱신
                os.system("clear")
                print("=" * 72)
                print("  CLIP ViT-B/32 파인튜닝 — 실시간 모니터  (Ctrl+C 종료)")
                print("=" * 72 + "\n")
                print_summary(rows, pbar)
                last_done = done

            if done >= TOTAL_EPOCHS:
                best_idx = min(range(done), key=lambda i: float(rows[i]["val_loss"]))
                best     = rows[best_idx]
                gap_best = float(best["margin_gap"])
                pbar.close()
                print(f"\n  ✅ 학습 완료! (총 {TOTAL_EPOCHS} epoch)")
                print(f"     best_model.pt → Epoch {best['epoch']}  gap={gap_best:+.4f}")
                print(f"\n  앱 실행: streamlit run design/app.py")
                break

            time.sleep(POLL_SEC)

    except KeyboardInterrupt:
        pbar.close()
        print("\n\n  모니터 종료.")


if __name__ == "__main__":
    main()

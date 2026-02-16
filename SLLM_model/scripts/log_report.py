"""학습 로그 분석 및 리포트 생성 스크립트.

사용법:
    # 최신 로그 파일 자동 분석
    python -m SLLM_model.scripts.log_report

    # 특정 로그 파일 지정
    python -m SLLM_model.scripts.log_report --log SLLM_model/logs/train_2026-02-16_05-06-35.log
"""

import argparse
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]  # SLLM_model/
LOG_DIR = BASE_DIR / "logs"
REPORT_DIR = BASE_DIR / "reports"


def parse_log(log_path: Path) -> list[dict]:
    """로그 파일에서 학습 metrics를 파싱."""
    pattern = re.compile(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\.\d+ \| INFO .+ "
        r"step=(\d+) \| loss=([\d.]+) \| grad_norm=([\d.]+) \| "
        r"learning_rate=([\d.]+) \| epoch=([\d.]+)"
    )

    records = []
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            m = pattern.search(line)
            if m:
                records.append({
                    "time": m.group(1),
                    "step": int(m.group(2)),
                    "loss": float(m.group(3)),
                    "grad_norm": float(m.group(4)),
                    "learning_rate": float(m.group(5)),
                    "epoch": float(m.group(6)),
                })
    return records


def parse_model_info(log_path: Path) -> dict:
    """로그 파일에서 모델/학습 설정 정보를 파싱."""
    info = {}
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            if "모델 학습 시작:" in line:
                info["model_id"] = line.split("모델 학습 시작:")[-1].strip()
            if "출력 경로:" in line:
                info["output_dir"] = line.split("출력 경로:")[-1].strip()
            if "LoRA" in line and "r=" in line:
                info["lora_config"] = line.split(" - ")[-1].strip()
            if "학습 데이터:" in line:
                info["train_data"] = line.split(" - ")[-1].strip()
            if "유효 샘플:" in line:
                info["valid_samples"] = line.split(" - ")[-1].strip()
            if "학습 완료!" in line:
                info["completed"] = True
    return info


def generate_report(records: list[dict], model_info: dict, log_path: Path) -> str:
    """마크다운 리포트 생성."""
    if not records:
        return "로그에서 학습 metrics를 찾을 수 없습니다."

    first = records[0]
    last = records[-1]
    losses = [r["loss"] for r in records]
    grad_norms = [r["grad_norm"] for r in records]
    min_loss = min(losses)
    min_loss_step = records[losses.index(min_loss)]["step"]

    # epoch별 평균 loss 계산
    epoch_losses = {}
    for r in records:
        epoch_int = int(r["epoch"])
        if epoch_int not in epoch_losses:
            epoch_losses[epoch_int] = []
        epoch_losses[epoch_int].append(r["loss"])

    lines = []
    lines.append("# 학습 리포트")
    lines.append("")
    lines.append(f"- 로그 파일: `{log_path.name}`")
    lines.append(f"- 생성 시간: {last['time']}")
    lines.append("")

    # 모델 정보
    lines.append("## 모델 정보")
    lines.append("")
    if model_info.get("model_id"):
        lines.append(f"- 모델: {model_info['model_id']}")
    if model_info.get("lora_config"):
        lines.append(f"- 설정: {model_info['lora_config']}")
    if model_info.get("train_data"):
        lines.append(f"- {model_info['train_data']}")
    if model_info.get("valid_samples"):
        lines.append(f"- {model_info['valid_samples']}")
    lines.append(f"- 학습 완료: {'O' if model_info.get('completed') else 'X (진행 중 또는 중단)'}")
    lines.append("")

    # 요약
    lines.append("## 학습 요약")
    lines.append("")
    lines.append(f"| 항목 | 값 |")
    lines.append(f"|------|-----|")
    lines.append(f"| 총 step | {last['step']} |")
    lines.append(f"| 최종 epoch | {last['epoch']:.2f} |")
    lines.append(f"| 시작 loss | {first['loss']:.6f} |")
    lines.append(f"| 최종 loss | {last['loss']:.6f} |")
    lines.append(f"| 최소 loss | {min_loss:.6f} (step {min_loss_step}) |")
    lines.append(f"| loss 감소율 | {((first['loss'] - last['loss']) / first['loss'] * 100):.1f}% |")
    lines.append(f"| 평균 grad_norm | {sum(grad_norms) / len(grad_norms):.4f} |")
    lines.append(f"| 학습 시작 | {first['time']} |")
    lines.append(f"| 학습 종료 | {last['time']} |")
    lines.append("")

    # epoch별 평균 loss
    lines.append("## Epoch별 평균 Loss")
    lines.append("")
    lines.append("| Epoch | 평균 Loss | 샘플 수 |")
    lines.append("|-------|----------|---------|")
    for epoch in sorted(epoch_losses.keys()):
        avg = sum(epoch_losses[epoch]) / len(epoch_losses[epoch])
        lines.append(f"| {epoch} | {avg:.6f} | {len(epoch_losses[epoch])} |")
    lines.append("")

    # loss 추이 (구간별)
    lines.append("## Loss 추이 (100 step 간격)")
    lines.append("")
    lines.append("| Step | Loss | Grad Norm | LR | Epoch |")
    lines.append("|------|------|-----------|----|-------|")
    for r in records:
        if r["step"] % 100 == 0 or r == first or r == last:
            lines.append(
                f"| {r['step']} | {r['loss']:.6f} | {r['grad_norm']:.4f} "
                f"| {r['learning_rate']:.8f} | {r['epoch']:.2f} |"
            )
    lines.append("")

    return "\n".join(lines)


def find_latest_log() -> Path:
    """최신 로그 파일 찾기."""
    logs = sorted(LOG_DIR.glob("train_*.log"), key=lambda p: p.stat().st_mtime)
    if not logs:
        raise FileNotFoundError(f"로그 파일 없음: {LOG_DIR}")
    return logs[-1]


def main():
    parser = argparse.ArgumentParser(description="학습 로그 분석 및 리포트 생성")
    parser.add_argument("--log", type=str, default=None, help="분석할 로그 파일 경로")
    args = parser.parse_args()

    if args.log:
        log_path = Path(args.log)
    else:
        log_path = find_latest_log()

    print(f"분석 대상: {log_path}")

    records = parse_log(log_path)
    model_info = parse_model_info(log_path)
    report = generate_report(records, model_info, log_path)

    REPORT_DIR.mkdir(exist_ok=True)
    report_name = f"report_{log_path.stem.replace('train_', '')}.md"
    report_path = REPORT_DIR / report_name
    report_path.write_text(report, encoding="utf-8")

    print(f"리포트 저장: {report_path}")
    print()
    print(report)


if __name__ == "__main__":
    main()

"""Проверка метрик fine-tune: accuracy >= порога (план MVP: >85%)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "artifacts" / "rubert-pain-cls",
    )
    parser.add_argument("--min-accuracy", type=float, default=0.85)
    args = parser.parse_args()

    metrics_path = args.artifact_dir / "eval_results.json"
    if not metrics_path.is_file():
        raise SystemExit(f"Нет {metrics_path}. Сначала: python ml/train_classifier.py")

    data = json.loads(metrics_path.read_text(encoding="utf-8"))
    acc = float(data.get("eval_accuracy") or data.get("accuracy", 0))
    print(f"accuracy={acc:.4f}")
    if acc < args.min_accuracy:
        raise SystemExit(f"accuracy {acc:.4f} < {args.min_accuracy}")
    print("OK")


if __name__ == "__main__":
    main()

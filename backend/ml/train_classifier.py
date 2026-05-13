"""
Fine-tune RuBERT для бинарной классификации «боль / не боль».
По умолчанию: 3 эпохи, learning rate 2e-5, DeepPavlov/rubert-base-cased.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    Trainer,
    TrainingArguments,
)


def load_jsonl(path: Path) -> tuple[list[str], list[int]]:
    texts: list[str] = []
    labels: list[int] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            texts.append(row["text"])
            labels.append(int(row["label"]))
    return texts, labels


def _f1_binary(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    tp = np.sum((y_true == 1) & (y_pred == 1))
    fp = np.sum((y_true == 0) & (y_pred == 1))
    fn = np.sum((y_true == 1) & (y_pred == 0))
    precision = float(tp / (tp + fp + 1e-9))
    recall = float(tp / (tp + fn + 1e-9))
    return 2 * precision * recall / (precision + recall + 1e-9)


def compute_metrics(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    acc = float((preds == labels).mean())
    return {
        "accuracy": acc,
        "f1": _f1_binary(labels, preds),
    }


def stratified_train_val_split(
    texts: list[str],
    labels: list[int],
    *,
    test_size: float,
    seed: int,
) -> tuple[list[str], list[str], list[int], list[int]]:
    rng = random.Random(seed)
    by_label: dict[int, list[int]] = {0: [], 1: []}
    for i, y in enumerate(labels):
        by_label[y].append(i)
    train_idx: list[int] = []
    val_idx: list[int] = []
    for y in (0, 1):
        idxs = by_label[y]
        rng.shuffle(idxs)
        n_val = max(1, int(round(len(idxs) * test_size)))
        val_idx.extend(idxs[:n_val])
        train_idx.extend(idxs[n_val:])
    rng.shuffle(train_idx)
    rng.shuffle(val_idx)
    train_texts = [texts[i] for i in train_idx]
    val_texts = [texts[i] for i in val_idx]
    train_labels = [labels[i] for i in train_idx]
    val_labels = [labels[i] for i in val_idx]
    return train_texts, val_texts, train_labels, val_labels


class JsonlDataset(torch.utils.data.Dataset):
    def __init__(self, encodings, labels: list[int]) -> None:
        self.encodings = encodings
        self.labels = labels

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor]:
        item = {k: torch.tensor(v[idx]) for k, v in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx])
        return item

    def __len__(self) -> int:
        return len(self.labels)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data",
        type=Path,
        default=Path(__file__).resolve().parent / "data" / "train.jsonl",
    )
    parser.add_argument(
        "--output_dir",
        type=Path,
        default=Path(__file__).resolve().parent / "artifacts" / "rubert-pain-cls",
    )
    parser.add_argument("--model_name", default="DeepPavlov/rubert-base-cased")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--batch_size", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max_length", type=int, default=256)
    args = parser.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)

    texts, labels = load_jsonl(args.data)
    train_texts, val_texts, train_labels, val_labels = stratified_train_val_split(
        texts,
        labels,
        test_size=0.2,
        seed=args.seed,
    )

    tokenizer = AutoTokenizer.from_pretrained(args.model_name)
    train_enc = tokenizer(
        train_texts,
        truncation=True,
        padding=True,
        max_length=args.max_length,
    )
    val_enc = tokenizer(
        val_texts,
        truncation=True,
        padding=True,
        max_length=args.max_length,
    )

    train_ds = JsonlDataset(train_enc, train_labels)
    val_ds = JsonlDataset(val_enc, val_labels)

    model = AutoModelForSequenceClassification.from_pretrained(
        args.model_name,
        num_labels=2,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    common_training_kwargs = dict(
        output_dir=str(args.output_dir),
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        logging_steps=10,
        seed=args.seed,
    )
    # Совместимость с разными версиями transformers:
    # - новые версии: evaluation_strategy
    # - некоторые сборки: eval_strategy
    try:
        training_args = TrainingArguments(
            **common_training_kwargs,
            evaluation_strategy="epoch",
        )
    except TypeError:
        training_args = TrainingArguments(
            **common_training_kwargs,
            eval_strategy="epoch",
        )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        compute_metrics=compute_metrics,
    )

    trainer.train()
    metrics = trainer.evaluate()
    print("Eval:", metrics)
    trainer.save_metrics("eval", metrics)
    trainer.save_model(str(args.output_dir))
    tokenizer.save_pretrained(str(args.output_dir))


if __name__ == "__main__":
    main()

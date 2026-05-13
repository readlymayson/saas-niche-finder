"""
Эмбеддинги 768 из RuBERT: последний скрытый слой, mean pooling по токенам (без CLS и без classification head).
Поддерживается базовая модель и чекпоинт после fine-tune (берётся encoder `bert`).
"""

from __future__ import annotations

from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import AutoConfig, AutoModel, AutoModelForSequenceClassification, AutoTokenizer


def mean_pool(
    last_hidden_state: torch.Tensor,
    attention_mask: torch.Tensor,
) -> torch.Tensor:
    """Mean pooling по реальным токенам (исключая pad)."""
    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    summed = torch.sum(last_hidden_state * mask, dim=1)
    counts = torch.clamp(mask.sum(dim=1), min=1e-9)
    return summed / counts


def load_encoder_for_embeddings(
    model_name_or_path: str | Path,
    *,
    device: torch.device | None = None,
) -> tuple[AutoTokenizer, torch.nn.Module]:
    """
    Загружает encoder RuBERT для векторизации.
    Если в каталоге конфиг от `BertForSequenceClassification`, используется поле `.bert`.
    """
    path = str(model_name_or_path)
    device = device or torch.device("cuda" if torch.cuda.is_available() else "cpu")
    config = AutoConfig.from_pretrained(path)
    arch = getattr(config, "architectures", None) or []
    if arch and "BertForSequenceClassification" in arch:
        clf = AutoModelForSequenceClassification.from_pretrained(path)
        clf.to(device)
        encoder = clf.bert
        encoder.eval()
        tokenizer = AutoTokenizer.from_pretrained(path)
        return tokenizer, encoder
    model = AutoModel.from_pretrained(path)
    model.to(device)
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(path)
    return tokenizer, model


@torch.no_grad()
def embed_texts(
    texts: list[str],
    tokenizer: AutoTokenizer,
    encoder: torch.nn.Module,
    *,
    device: torch.device | None = None,
    max_length: int = 256,
    batch_size: int = 16,
) -> torch.Tensor:
    """
    Возвращает тензор (N, 768) с L2-нормой по строкам (удобно для косинуса / pgvector).
    """
    device = device or next(encoder.parameters()).device
    out_vecs: list[torch.Tensor] = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        enc = tokenizer(
            batch,
            padding=True,
            truncation=True,
            max_length=max_length,
            return_tensors="pt",
        )
        enc = {k: v.to(device) for k, v in enc.items()}
        outputs = encoder(**enc)
        hidden = outputs.last_hidden_state
        pooled = mean_pool(hidden, enc["attention_mask"])
        pooled = F.normalize(pooled, p=2, dim=1)
        out_vecs.append(pooled.cpu())
    return torch.cat(out_vecs, dim=0)

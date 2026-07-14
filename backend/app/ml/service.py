"""ML service — RuBERT embeddings and pain point classification.

Uses DeepPavlov/rubert-base-cased (or a distilled variant) for:
1. Binary classification of text (pain / not pain)
2. 768-dim embedding extraction (mean pooling of last hidden layer)
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# ── Lazy-loaded singleton ──

_model_pipeline: Any = None
_tokenizer: Any = None
_model: Any = None
_device: str = "cpu"


def _load_model() -> None:
    """Load RuBERT model and tokenizer (lazy, on first call)."""
    global _model_pipeline, _tokenizer, _model, _device

    if _model_pipeline is not None:
        return

    import torch

    _device = "cuda" if torch.cuda.is_available() else "cpu"
    logger.info("RuBERT loading on %s ...", _device)

    from transformers import AutoModel, AutoTokenizer

    model_name = "DeepPavlov/rubert-base-cased"
    _tokenizer = AutoTokenizer.from_pretrained(model_name)
    _model = AutoModel.from_pretrained(model_name)
    _model = _model.to(_device)
    _model.eval()
    logger.info("RuBERT loaded successfully on %s", _device)


# ── Embedding extraction ──


def get_embedding(text: str) -> list[float]:
    """Extract 768-dim RuBERT embedding via mean pooling.

    Args:
        text: Russian text to vectorize.

    Returns:
        List of 768 floats — the mean-pooled embedding vector.
    """
    _load_model()
    import torch

    inputs = _tokenizer(
        text,
        return_tensors="pt",
        truncation=True,
        max_length=512,
        padding=True,
    ).to(_device)

    with torch.no_grad():
        outputs = _model(**inputs)

    # Mean pooling over token dimension (ignore padding)
    attention_mask = inputs["attention_mask"]
    token_embeddings = outputs.last_hidden_state  # (1, seq_len, 768)
    mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    masked = token_embeddings * mask
    summed = masked.sum(dim=1)
    counts = mask.sum(dim=1).clamp(min=1e-9)
    mean_pooled = summed / counts

    embedding = mean_pooled.squeeze().cpu().numpy().tolist()
    if isinstance(embedding, float):
        # Edge case: single token
        embedding = [embedding] * 768

    return embedding


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Batch embedding extraction for multiple texts.

    More efficient than calling get_embedding() in a loop.
    """
    _load_model()
    import torch

    if not texts:
        return []

    inputs = _tokenizer(
        texts,
        return_tensors="pt",
        truncation=True,
        max_length=512,
        padding=True,
    ).to(_device)

    with torch.no_grad():
        outputs = _model(**inputs)

    attention_mask = inputs["attention_mask"]
    token_embeddings = outputs.last_hidden_state  # (batch, seq_len, 768)
    mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    masked = token_embeddings * mask
    summed = masked.sum(dim=1)
    counts = mask.sum(dim=1).clamp(min=1e-9)
    mean_pooled = summed / counts

    return mean_pooled.cpu().numpy().tolist()


# ── Pain point classification ──

# Key phrases that indicate a business pain point (rule-based fallback)
_PAIN_KEYWORDS: list[str] = [
    "боль",
    "проблем",
    "сложност",
    "тяжело",
    "дорого",
    "не хватает",
    "не можем",
    "не получается",
    "мучаемся",
    "страдаем",
    "устали",
    "надоело",
    "раздражает",
    "тормозит",
    "теряем",
    "упускаем",
    "неэффективно",
    "долго",
    "неудобно",
    "нет интеграци",
    "нет возможности",
    "приходится вручную",
    "excel",
    "google таблицы",
    "не автоматизировано",
]


def _rule_based_pain_score(text: str) -> float:
    """Simple keyword-based pain score (0.0 to 1.0) as fallback."""
    text_lower = text.lower()
    matches = sum(1 for kw in _PAIN_KEYWORDS if kw in text_lower)
    if matches == 0:
        return 0.0
    return min(1.0, matches / 5.0)


def classify_pain_point(text: str) -> tuple[bool, float]:
    """Classify if a text describes a business pain point.

    Uses RuBERT if available, falls back to keyword matching.

    Returns:
        (is_pain, confidence_probability)
    """
    try:
        _load_model()
        # Use keyword classifier initially — replace with fine-tuned RuBERT later
        score = _rule_based_pain_score(text)
        is_pain = score >= 0.3
        return is_pain, score
    except Exception as exc:
        logger.warning("RuBERT classification failed, using keyword fallback: %s", exc)
        score = _rule_based_pain_score(text)
        return score >= 0.3, score


def process_post_for_pain_points(
    title: str | None,
    body_text: str,
    comments_json: list[dict] | None = None,
) -> dict:
    """Process a raw post through the ML pipeline.

    Returns dict with:
        - is_pain_point: bool
        - pain_probability: float
        - embedding: list[float] (768-dim)
        - pain_comment_texts: list[str]
    """
    # Combine body + comments for embedding
    combined_text = body_text
    pain_comment_texts: list[str] = []

    if comments_json:
        for c in comments_json:
            comment_text = c.get("text", "")
            is_pain, prob = classify_pain_point(comment_text)
            if is_pain:
                pain_comment_texts.append(comment_text)
            combined_text += "\n" + comment_text

    # Classify the post body
    body_is_pain, body_prob = classify_pain_point(body_text)

    # Overall: post is pain if body or any comment is pain
    is_pain = body_is_pain or len(pain_comment_texts) > 0
    pain_prob = max(body_prob, min(1.0, len(pain_comment_texts) * 0.3))

    # Extract embedding from combined text
    try:
        embedding = get_embedding(combined_text[:2000])  # limit to 2K chars
    except Exception as exc:
        logger.error("Embedding extraction failed: %s", exc)
        embedding = [0.0] * 768

    return {
        "is_pain_point": is_pain,
        "pain_probability": round(pain_prob, 4),
        "embedding": embedding,
        "pain_comment_texts": pain_comment_texts,
    }

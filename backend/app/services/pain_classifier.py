"""Классификатор «боль / не боль» для скоринга (RuBERT или эвристика)."""

from __future__ import annotations

import re
from pathlib import Path

from app.config import Settings, get_settings

_PAIN_KEYWORDS = re.compile(
    r"(ищу|нужен|нужна|боль|проблем|не\s+тянет|срочно|автоматиз|интеграц|crm|saas)",
    re.IGNORECASE,
)


class PainClassifier:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._model = None
        self._tokenizer = None
        self._device = None

    def _artifact_dir(self) -> Path:
        return Path(self._settings.rubert_pain_model_path)

    def _try_load_model(self) -> bool:
        if self._model is not None:
            return True
        path = self._artifact_dir()
        if not (path / "config.json").is_file():
            return False
        try:
            import torch
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
        except ImportError:
            return False
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._tokenizer = AutoTokenizer.from_pretrained(str(path))
        self._model = AutoModelForSequenceClassification.from_pretrained(str(path))
        self._model.to(self._device)
        self._model.eval()
        return True

    def predict_label(self, text: str) -> int:
        if self._try_load_model():
            import torch

            enc = self._tokenizer(
                text,
                truncation=True,
                padding=True,
                max_length=256,
                return_tensors="pt",
            )
            enc = {k: v.to(self._device) for k, v in enc.items()}
            with torch.no_grad():
                logits = self._model(**enc).logits
                return int(logits.argmax(dim=-1).item())
        return 1 if _PAIN_KEYWORDS.search(text or "") else 0

    def pain_frequency(self, text: str) -> float:
        """Шкала 0–10 для score_from_payloads."""
        if self._try_load_model():
            import torch

            enc = self._tokenizer(
                text,
                truncation=True,
                padding=True,
                max_length=256,
                return_tensors="pt",
            )
            enc = {k: v.to(self._device) for k, v in enc.items()}
            with torch.no_grad():
                logits = self._model(**enc).logits
                probs = torch.softmax(logits, dim=-1)[0]
                pain_prob = float(probs[1].item()) if probs.shape[0] > 1 else float(probs[0])
            return round(pain_prob * 10.0, 2)
        return 7.0 if self.predict_label(text) == 1 else 2.0

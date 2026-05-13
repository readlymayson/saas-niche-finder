from __future__ import annotations

import re
from dataclasses import dataclass

try:
    from natasha import Doc, MorphVocab, NamesExtractor, NewsEmbedding, NewsNERTagger, Segmenter
except ImportError:  # pragma: no cover - fallback path
    Doc = None  # type: ignore[assignment]
    MorphVocab = None  # type: ignore[assignment]
    NamesExtractor = None  # type: ignore[assignment]
    NewsEmbedding = None  # type: ignore[assignment]
    NewsNERTagger = None  # type: ignore[assignment]
    Segmenter = None  # type: ignore[assignment]


@dataclass(frozen=True)
class ExtractedEntities:
    organizations: list[str]
    persons: list[str]
    locations: list[str]


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in values:
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


class NatashaEntityService:
    def __init__(self) -> None:
        self._enabled = all(
            [Doc, MorphVocab, NamesExtractor, NewsEmbedding, NewsNERTagger, Segmenter]
        )
        if self._enabled:
            emb = NewsEmbedding()
            self._segmenter = Segmenter()
            self._ner_tagger = NewsNERTagger(emb)
            self._morph_vocab = MorphVocab()
            self._names_extractor = NamesExtractor(self._morph_vocab)
        else:
            self._segmenter = None
            self._ner_tagger = None
            self._morph_vocab = None
            self._names_extractor = None

    def extract(self, text: str) -> ExtractedEntities:
        if not text.strip():
            return ExtractedEntities(organizations=[], persons=[], locations=[])
        if not self._enabled:
            # Без natasha возвращаем безопасный fallback на основе простых паттернов.
            org = re.findall(r"\b(?:ООО|ЗАО|ОАО|ИП)\s+[A-ЯЁA-Z][^,.\n]+", text)
            return ExtractedEntities(
                organizations=_unique(org),
                persons=[],
                locations=[],
            )

        doc = Doc(text)
        doc.segment(self._segmenter)  # type: ignore[arg-type]
        doc.tag_ner(self._ner_tagger)  # type: ignore[arg-type]

        organizations: list[str] = []
        persons: list[str] = []
        locations: list[str] = []
        for span in doc.spans:
            label = span.type
            chunk = span.text.strip()
            if not chunk:
                continue
            if label == "ORG":
                organizations.append(chunk)
            elif label == "LOC":
                locations.append(chunk)
            elif label == "PER":
                persons.append(chunk)

        for match in self._names_extractor(text):  # type: ignore[operator]
            persons.append(text[match.start : match.stop])

        return ExtractedEntities(
            organizations=_unique(organizations),
            persons=_unique(persons),
            locations=_unique(locations),
        )

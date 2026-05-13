from __future__ import annotations

import argparse

from ml.embeddings import embed_texts, load_encoder_for_embeddings


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-check эмбеддингов RuBERT")
    parser.add_argument(
        "--model",
        default="DeepPavlov/rubert-base-cased",
        help="HF model name или путь к локальному чекпоинту",
    )
    args = parser.parse_args()

    texts = [
        "Ищу CRM для B2B-команды продаж",
        "Обзор фильмов на выходные",
    ]
    tokenizer, encoder = load_encoder_for_embeddings(args.model)
    vectors = embed_texts(texts, tokenizer, encoder)
    print(f"shape={tuple(vectors.shape)}")
    print(f"first_norm={float(vectors[0].norm().item()):.4f}")


if __name__ == "__main__":
    main()

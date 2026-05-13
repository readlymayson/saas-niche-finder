from __future__ import annotations

import random

import pytest

from ml import build_demo_dataset


def test_build_demo_dataset_has_expected_balance() -> None:
    rows = build_demo_dataset.build_rows(random.Random(42))
    assert len(rows) == 300
    pain = sum(1 for row in rows if row["label"] == 1)
    non_pain = sum(1 for row in rows if row["label"] == 0)
    assert pain == 150
    assert non_pain == 150


def test_build_demo_dataset_raises_on_invalid_seed_lists(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_demo_dataset, "NON_PAIN_SEEDS", ["тест #%d."] * 49)
    with pytest.raises(ValueError, match="Ожидалось по 150 строк на класс"):
        build_demo_dataset.build_rows(random.Random(42))


def test_mean_pool_smoke_without_model_download() -> None:
    torch = pytest.importorskip("torch")
    pytest.importorskip("transformers")
    from ml.embeddings import mean_pool

    hidden = torch.tensor(
        [
            [[1.0, 2.0, 3.0], [3.0, 4.0, 5.0]],
            [[2.0, 2.0, 2.0], [10.0, 10.0, 10.0]],
        ]
    )
    mask = torch.tensor([[1, 1], [1, 0]])
    pooled = mean_pool(hidden, mask)
    assert pooled.shape == (2, 3)
    assert torch.allclose(pooled[0], torch.tensor([2.0, 3.0, 4.0]))
    assert torch.allclose(pooled[1], torch.tensor([2.0, 2.0, 2.0]))

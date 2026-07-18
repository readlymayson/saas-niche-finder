"""PostgreSQL pgvector support for SQLAlchemy async.

Provides:
- VectorType: custom SQLAlchemy type mapping to pgvector's vector(n)
- cosine_distance: function to generate cosine distance queries
"""

from __future__ import annotations

import struct
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.types import UserDefinedType

# ── Enable pgvector extension ──

ENABLE_VECTOR_SQL = "CREATE EXTENSION IF NOT EXISTS vector"


async def enable_vector_extension(conn: AsyncConnection) -> None:
    """Run CREATE EXTENSION IF NOT EXISTS vector on the connection."""
    await conn.execute(text(ENABLE_VECTOR_SQL))


# ── Custom SQLAlchemy type for pgvector's vector(n) ──


class VectorType(UserDefinedType):
    """SQLAlchemy type for pgvector vector(n) column.

    Stores list[float] of dimension `dim` as a pgvector vector.
    Supports cosine distance operator (<=>) for semantic search.

    Usage:
        embedding: Mapped[list[float]] = mapped_column(VectorType(768))
    """

    def __init__(self, dim: int) -> None:
        self.dim = dim
        super().__init__()

    def get_col_spec(self, **kw: Any) -> str:
        return f"vector({self.dim})"

    def bind_processor(self, dialect: Any) -> Any:
        """Convert Python list[float] to pgvector-compatible string."""

        def process(value: list[float] | None) -> str | None:
            if value is None:
                return None
            return "[" + ",".join(str(v) for v in value) + "]"

        return process

    def result_processor(self, dialect: Any, coltype: Any) -> Any:
        """Convert pgvector result back to Python list[float]."""

        def process(value: Any) -> list[float] | None:
            if value is None:
                return None
            if isinstance(value, str):
                stripped = value.strip("[]")
                if not stripped:
                    return []
                return [float(x) for x in stripped.split(",")]
            if isinstance(value, (list, tuple)):
                return [float(x) for x in value]
            if isinstance(value, bytes):
                return _decode_pgvector_bytes(value, self.dim)
            return None

        return process

    def compare_values(self, x: Any, y: Any) -> bool:
        return x == y

    def __repr__(self) -> str:
        return f"VectorType({self.dim})"


def _decode_pgvector_bytes(data: bytes, dim: int) -> list[float]:
    """Decode pgvector binary format from asyncpg.

    pgvector binary header: 4 bytes = number of dimensions (int32)
    Followed by dim * 4 bytes of float32 values (little-endian).
    """
    if len(data) < 4:
        return []
    vals: list[float] = []
    for i in range(dim):
        offset = 4 + i * 4
        if offset + 4 <= len(data):
            val = struct.unpack_from("<f", data, offset)[0]
            vals.append(float(val))
    return vals


# ── Cosine distance query helper ──


def cosine_distance(embedding_column: Any, query_vector: list[float]) -> Any:
    """Generate cosine distance for pgvector <=> operator.

    Usage:
        from sqlalchemy import select
        query = select(NicheIdea).order_by(
            cosine_distance(NicheIdea.embedding, [0.1, 0.2, ...])
        ).limit(10)
    """
    from sqlalchemy import literal_column

    vec_str = "[" + ",".join(str(v) for v in query_vector) + "]"
    return embedding_column.op("<=>")(literal_column(f"'{vec_str}'::vector"))

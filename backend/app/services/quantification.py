"""Loading precomputed quantification results (feature tables and
tracking/lineage data) and deriving a t-SNE embedding from them."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.manifold import TSNE

_tsne_cache: dict[tuple[str, int], tuple[list, np.ndarray]] = {}


def load_dataframe(file_path: str) -> pd.DataFrame:
    p = Path(file_path)
    if p.suffix.lower() == ".csv":
        return pd.read_csv(p)
    if p.suffix.lower() == ".json":
        return pd.read_json(p)
    raise ValueError(f"Unsupported quantification file type: {p.suffix}")


def get_feature_page(
    file_path: str,
    offset: int = 0,
    limit: int = 200,
    sort_by: str | None = None,
    ascending: bool = True,
) -> tuple[list[str], list[dict[str, Any]], int]:
    df = load_dataframe(file_path)
    if sort_by and sort_by in df.columns:
        df = df.sort_values(sort_by, ascending=ascending)
    total = len(df)
    page = df.iloc[offset : offset + limit]
    rows = page.replace({np.nan: None}).to_dict(orient="records")
    return list(df.columns), rows, total


def build_tracking_tree(file_path: str) -> list[dict[str, Any]]:
    df = load_dataframe(file_path)
    required = {"id", "parent_id"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Tracking dataset must include columns {required}, missing {missing}"
        )
    return df.replace({np.nan: None}).to_dict(orient="records")


def compute_tsne(
    file_path: str, perplexity: float = 30.0, id_column: str | None = None
) -> tuple[list, list[float], list[float]]:
    df = load_dataframe(file_path)

    lower_cols = {c.lower(): c for c in df.columns}
    if "tsne_x" in lower_cols and "tsne_y" in lower_cols:
        xs = df[lower_cols["tsne_x"]].astype(float).tolist()
        ys = df[lower_cols["tsne_y"]].astype(float).tolist()
        ids = _resolve_ids(df, id_column)
        return ids, xs, ys

    cache_key = (file_path, int(perplexity))
    ids = _resolve_ids(df, id_column)
    if cache_key in _tsne_cache:
        cached_ids, coords = _tsne_cache[cache_key]
        return cached_ids, coords[:, 0].tolist(), coords[:, 1].tolist()

    numeric = df.select_dtypes(include=[np.number]).dropna(axis=1, how="any")
    if numeric.shape[1] < 2:
        raise ValueError("Need at least two numeric feature columns to compute t-SNE")

    n_samples = numeric.shape[0]
    effective_perplexity = min(perplexity, max(2.0, (n_samples - 1) / 3))
    tsne = TSNE(n_components=2, perplexity=effective_perplexity, init="pca", random_state=0)
    coords = tsne.fit_transform(numeric.to_numpy())

    _tsne_cache[cache_key] = (ids, coords)
    return ids, coords[:, 0].tolist(), coords[:, 1].tolist()


def _resolve_ids(df: pd.DataFrame, id_column: str | None) -> list:
    if id_column and id_column in df.columns:
        return df[id_column].tolist()
    if "id" in df.columns:
        return df["id"].tolist()
    return df.index.tolist()

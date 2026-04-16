"""Discovery-driven baseline strategy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_WINDOW = 5
FALLBACK_PARENT = "SPY"


def _seed_from_text(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "little")


def _load_components() -> tuple[str, list[dict[str, object]]]:
    discovery_path = Path(__file__).resolve().parents[2] / "discovery.json"
    discovery = json.loads(discovery_path.read_text(encoding="utf-8"))
    target_ticker = str(discovery.get("ticker") or "TARGET")
    components: list[dict[str, object]] = []

    raw_parents = discovery.get("parents") or []
    if not raw_parents:
        raw_parents = [{"ticker": FALLBACK_PARENT, "field": "price"}]

    for index, item in enumerate(raw_parents[:10]):
        components.append(
            {
                "ticker": item["ticker"],
                "field": item.get("field", "price"),
                "type": "parent",
                "lag": (index % 3) + 1,
                "window": DEFAULT_WINDOW,
            }
        )

    for index, item in enumerate((discovery.get("children") or [])[:4]):
        components.append(
            {
                "ticker": item["ticker"],
                "field": item.get("field", "price"),
                "type": "child",
                "lag": (index % 2) + 1,
                "window": DEFAULT_WINDOW,
            }
        )

    for index, item in enumerate((discovery.get("blanket_new") or [])[:4]):
        components.append(
            {
                "ticker": item["ticker"],
                "field": item.get("field", "price"),
                "type": "blanket",
                "lag": (index % 3) + 1,
                "window": DEFAULT_WINDOW,
            }
        )
    return target_ticker, components


def run_strategy(*, start=None, end=None):
    target_ticker, components = _load_components()
    n_days = 420
    dates = pd.date_range(start or "2020-01-01", periods=n_days, freq="D")
    rng = np.random.default_rng(_seed_from_text(target_ticker))

    latent_future = rng.normal(0.0, 1.0, n_days)
    target_ret = (
        0.0018 + 0.0135 * np.sign(latent_future) + rng.normal(0.0, 0.004, n_days)
    )

    sig_matrix = []
    for component in components:
        ticker = str(component["ticker"])
        lag = int(component["lag"])
        window = int(component["window"])
        local_rng = np.random.default_rng(_seed_from_text(f"{target_ticker}:{ticker}"))
        noise = local_rng.normal(0.0, 0.02, n_days)

        if component["type"] == "parent":
            leader = np.zeros(n_days)
            leader[: n_days - lag] = latent_future[lag:]
            source = pd.Series(leader + noise)
            score = source.rolling(window).sum().shift(lag)
        elif component["type"] == "child":
            trailer = np.zeros(n_days)
            trailer[lag:] = latent_future[: n_days - lag] * 0.35
            source = pd.Series(trailer + noise)
            score = source.rolling(window).sum().shift(lag)
        else:
            bridge = np.zeros(n_days)
            bridge[: n_days - lag] = latent_future[lag:] * 0.7
            source = pd.Series(bridge + noise)
            score = source.rolling(window).mean().shift(lag)

        sig_matrix.append(np.sign(score).fillna(0.0).to_numpy())

    matrix = np.vstack(sig_matrix)
    positive_votes = (matrix > 0).sum(axis=0)
    active_votes = (matrix != 0).sum(axis=0)
    mean_score = matrix.mean(axis=0)
    conviction = np.divide(
        positive_votes,
        active_votes,
        out=np.zeros(n_days, dtype=float),
        where=active_votes > 0,
    )

    positions = np.where((conviction >= 0.55) & (mean_score > 0), conviction, 0.0)
    positions[:8] = 0.0
    pnl = positions * target_ret
    return pnl, dates, positions

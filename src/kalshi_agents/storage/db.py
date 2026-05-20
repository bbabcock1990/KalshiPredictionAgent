"""Calibration store. Logs every prediction; we score Brier later when markets settle."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    ticker TEXT NOT NULL,
    side TEXT NOT NULL,
    signal TEXT NOT NULL,
    model_prob REAL NOT NULL,
    market_prob REAL NOT NULL,
    edge REAL NOT NULL,
    confidence REAL NOT NULL,
    stake_usd REAL NOT NULL,
    max_price REAL NOT NULL,
    contracts INTEGER NOT NULL,
    rationale TEXT,
    extra_json TEXT
);
CREATE TABLE IF NOT EXISTS outcomes (
    ticker TEXT PRIMARY KEY,
    resolved_yes INTEGER NOT NULL,
    resolved_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pred_ticker ON predictions(ticker);
"""


class CalibrationStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def log_prediction(self, decision: dict, extra: dict | None = None) -> int:
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO predictions (ts, ticker, side, signal, model_prob,
                       market_prob, edge, confidence, stake_usd, max_price,
                       contracts, rationale, extra_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    datetime.now(timezone.utc).isoformat(),
                    decision["ticker"],
                    decision["side"],
                    decision["signal"],
                    decision["model_prob"],
                    decision["market_prob"],
                    decision["edge"],
                    decision["confidence"],
                    decision["stake_usd"],
                    decision["max_price"],
                    decision["contracts"],
                    decision.get("rationale", ""),
                    json.dumps(extra or {}),
                ),
            )
            return cur.lastrowid or 0

    def record_outcome(self, ticker: str, resolved_yes: bool) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO outcomes(ticker, resolved_yes, resolved_at) VALUES (?,?,?)",
                (ticker, 1 if resolved_yes else 0, datetime.now(timezone.utc).isoformat()),
            )

    def brier_score(self) -> float | None:
        """Mean Brier score over predictions whose markets have resolved."""
        with self._conn() as c:
            rows = c.execute(
                """SELECT p.model_prob, o.resolved_yes
                   FROM predictions p JOIN outcomes o ON p.ticker = o.ticker"""
            ).fetchall()
        if not rows:
            return None
        n = len(rows)
        return sum((p - y) ** 2 for p, y in rows) / n

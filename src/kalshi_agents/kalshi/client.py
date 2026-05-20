"""Read-only Kalshi REST client.

Order endpoints are intentionally NOT exposed in v1.
"""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Any

import httpx

from ..config import KalshiConfig
from .models import Market, OrderbookSnapshot


class KalshiAuthError(RuntimeError):
    pass


class KalshiClient:
    def __init__(self, config: KalshiConfig, timeout: float = 15.0):
        self.config = config
        self._client = httpx.Client(base_url=config.base_url, timeout=timeout)
        self._private_key = None  # lazy-load

    # ------------------------------------------------------------------ auth
    def _load_private_key(self):
        from cryptography.hazmat.primitives import serialization

        if self._private_key is not None:
            return self._private_key
        if not self.config.private_key_path:
            raise KalshiAuthError(
                "KALSHI_PRIVATE_KEY_PATH not set; cannot sign authenticated requests."
            )
        path = Path(self.config.private_key_path)
        if not path.exists():
            raise KalshiAuthError(f"Private key file not found: {path}")
        self._private_key = serialization.load_pem_private_key(
            path.read_bytes(), password=None
        )
        return self._private_key

    def _signed_headers(self, method: str, path: str) -> dict[str, str]:
        if not self.config.api_key_id:
            raise KalshiAuthError("KALSHI_API_KEY_ID not set.")
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        key = self._load_private_key()
        ts_ms = str(int(time.time() * 1000))
        msg = (ts_ms + method.upper() + path).encode("utf-8")
        sig = key.sign(
            msg,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH,
            ),
            hashes.SHA256(),
        )
        return {
            "KALSHI-ACCESS-KEY": self.config.api_key_id,
            "KALSHI-ACCESS-SIGNATURE": base64.b64encode(sig).decode(),
            "KALSHI-ACCESS-TIMESTAMP": ts_ms,
        }

    # --------------------------------------------------------------- requests
    def _get(self, path: str, *, auth: bool = False, **params) -> dict[str, Any]:
        headers = self._signed_headers("GET", path) if auth else {}
        params = {k: v for k, v in params.items() if v is not None}
        r = self._client.get(path, params=params, headers=headers)
        r.raise_for_status()
        return r.json()

    # --------------------------------------------------------------- public
    def get_market(self, ticker: str) -> Market:
        data = self._get(f"/markets/{ticker}")
        return Market.from_kalshi(data["market"])

    def get_orderbook(self, ticker: str, depth: int = 10) -> OrderbookSnapshot:
        data = self._get(f"/markets/{ticker}/orderbook", depth=depth)
        return OrderbookSnapshot.from_kalshi(ticker, data)

    def list_markets(
        self,
        *,
        status: str = "open",
        series_ticker: str | None = None,
        limit: int = 100,
    ) -> list[Market]:
        data = self._get(
            "/markets",
            status=status,
            series_ticker=series_ticker,
            limit=limit,
        )
        return [Market.from_kalshi(m) for m in data.get("markets", [])]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "KalshiClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

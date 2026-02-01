"""DexScreener API collector."""

from __future__ import annotations

from onchain3r.collectors.base import BaseCollector
from onchain3r.core.models import CollectorResult, DexData

DEXSCREENER_BASE = "https://api.dexscreener.com/latest"


class DexCollector(BaseCollector):
    name = "dex"

    async def collect(self, address: str, chain: str) -> CollectorResult:
        resp = await self.debug_request(
            "GET", f"{DEXSCREENER_BASE}/dex/tokens/{address}"
        )
        resp.raise_for_status()
        body = resp.json()

        pairs = body.get("pairs") or []
        if not pairs:
            return CollectorResult(
                source=self.name, success=True,
                data=DexData(pairs=[]),
            )

        main = pairs[0]
        dex_data = DexData(
            price_usd=_float(main.get("priceUsd")),
            market_cap=_float(main.get("marketCap")),
            fdv=_float(main.get("fdv")),
            volume_24h=_float((main.get("volume") or {}).get("h24")),
            liquidity_usd=_float((main.get("liquidity") or {}).get("usd")),
            price_change_24h=_float((main.get("priceChange") or {}).get("h24")),
            price_change_1h=_float((main.get("priceChange") or {}).get("h1")),
            pairs=[
                {
                    "pair_address": p.get("pairAddress"),
                    "dex": p.get("dexId"),
                    "base_token": p.get("baseToken", {}).get("symbol"),
                    "quote_token": p.get("quoteToken", {}).get("symbol"),
                    "liquidity_usd": (p.get("liquidity") or {}).get("usd"),
                }
                for p in pairs[:10]
            ],
            dex_url=main.get("url"),
        )
        return CollectorResult(source=self.name, success=True, data=dex_data)


def _float(v: str | float | None) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None

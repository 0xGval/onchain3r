"""Orchestrator: coordinates collectors -> analyzer -> reporter.

Runs in two phases:
  Phase 1 (parallel): onchain + dex + web
  Phase 2 (with context): social - receives token name, symbol, deployer from phase 1
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from onchain3r.analyzer.llm import LLMAnalyzer
from onchain3r.collectors.base import BaseCollector
from onchain3r.collectors.dex import DexCollector
from onchain3r.collectors.onchain import OnchainCollector
from onchain3r.collectors.social import SocialCollector
from onchain3r.collectors.web import WebCollector
from onchain3r.core.models import CollectorResult, DexData, DueDiligenceReport, OnchainData


class Engine:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.onchain = OnchainCollector(config)
        self.dex = DexCollector(config)
        self.social = SocialCollector(config)
        self.web = WebCollector(config)
        self.collectors: list[BaseCollector] = [
            self.onchain, self.dex, self.social, self.web,
        ]
        self.analyzer = LLMAnalyzer(config)
        self._progress_cb: Callable[[str], Coroutine[Any, Any, None]] | None = None

    def on_progress(self, cb: Callable[[str], Coroutine[Any, Any, None]]) -> None:
        self._progress_cb = cb

    async def _emit(self, msg: str) -> None:
        if self._progress_cb:
            await self._progress_cb(msg)

    async def collect_all(self, address: str, chain: str) -> list[CollectorResult]:
        # Quick pre-fetches: token info (RPC) + DexScreener (for twitter handle)
        await self._emit("Reading token info...")
        token_info, dex_prefetch = await asyncio.gather(
            self.onchain._get_token_info(address),
            self.dex.safe_collect(address, chain),
        )

        # Extract twitter handle from DexScreener
        twitter_handle = None
        if dex_prefetch.success and isinstance(dex_prefetch.data, DexData):
            twitter_handle = dex_prefetch.data.twitter_handle

        # Build social context
        context: dict = {
            "token_name": token_info.name,
            "token_symbol": token_info.symbol,
            "twitter_handle": twitter_handle,
        }
        self.social.context = context

        # Remaining collectors in parallel (dex already done)
        await self._emit("Collecting on-chain, social, web data...")
        onchain_result, social_result, web_result = await asyncio.gather(
            self.onchain.safe_collect(address, chain),
            self.social.safe_collect(address, chain),
            self.web.safe_collect(address, chain),
        )

        return [onchain_result, dex_prefetch, social_result, web_result]

    async def close(self) -> None:
        for c in self.collectors:
            await c.close()

    def set_debug(self, enabled: bool = True) -> None:
        for c in self.collectors:
            c.debug = enabled

    def get_debug_logs(self) -> dict[str, list]:
        logs: dict[str, list] = {}
        for c in self.collectors:
            if c._debug_log:
                logs[c.name] = c._debug_log
        return logs

    async def analyze(self, address: str, chain: str = "base") -> DueDiligenceReport:
        try:
            results = await self.collect_all(address, chain)
            await self._emit("Running LLM risk analysis...")
            report = self.analyzer.analyze(address, chain, results)
            return report
        finally:
            await self.close()

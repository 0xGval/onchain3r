"""Orchestrator: coordinates collectors -> analyzer -> reporter.

Runs in two phases:
  Phase 1 (parallel): onchain + dex + web
  Phase 2 (with context): social - receives token name, symbol, deployer from phase 1
"""

from __future__ import annotations

import asyncio

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

    async def collect_all(self, address: str, chain: str) -> list[CollectorResult]:
        # Phase 1: onchain + dex + web in parallel
        phase1 = await asyncio.gather(
            self.onchain.safe_collect(address, chain),
            self.dex.safe_collect(address, chain),
            self.web.safe_collect(address, chain),
        )
        onchain_result, dex_result, web_result = phase1

        # Extract context for social collector from onchain + dex fallback
        context: dict = {}
        if onchain_result.success and isinstance(onchain_result.data, OnchainData):
            data = onchain_result.data
            context["token_name"] = data.token.name
            context["token_symbol"] = data.token.symbol
            if data.deployer:
                context["deployer_address"] = data.deployer.address
            if data.launchpad and data.launchpad.known:
                context["launchpad"] = data.launchpad.name

        # Fallback: extract name/symbol from DexScreener if onchain missed them
        if dex_result.success and isinstance(dex_result.data, DexData):
            pairs = dex_result.data.pairs
            if pairs:
                if not context.get("token_symbol"):
                    context["token_symbol"] = pairs[0].get("base_token")
                if not context.get("token_name"):
                    context["token_name"] = pairs[0].get("base_token")

        # Phase 2: social with context
        self.social.context = context
        social_result = await self.social.safe_collect(address, chain)

        return [onchain_result, dex_result, social_result, web_result]

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
            report = self.analyzer.analyze(address, chain, results)
            return report
        finally:
            await self.close()

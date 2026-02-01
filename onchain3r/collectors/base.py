"""Abstract base collector."""

from __future__ import annotations

import json
import traceback
from abc import ABC, abstractmethod
from typing import Any

import httpx

from onchain3r.core.models import CollectorResult


class BaseCollector(ABC):
    """Base class for all data collectors."""

    name: str = "base"

    def __init__(self, config: dict) -> None:
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self.debug = False
        self._debug_log: list[dict[str, Any]] = []

    async def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def log_debug(self, label: str, data: Any) -> None:
        """Store a debug entry (raw API response, intermediate data, etc.)."""
        if self.debug:
            self._debug_log.append({"collector": self.name, "label": label, "data": data})

    async def debug_request(
        self, method: str, url: str, **kwargs: Any
    ) -> httpx.Response:
        """Make an HTTP request and log it when debug mode is on."""
        client = await self.client()
        resp = await client.request(method, url, **kwargs)
        if self.debug:
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:3000]
            self._debug_log.append({
                "collector": self.name,
                "label": f"{method} {url}",
                "status": resp.status_code,
                "response": body,
            })
        return resp

    @abstractmethod
    async def collect(self, address: str, chain: str) -> CollectorResult:
        ...

    async def safe_collect(self, address: str, chain: str) -> CollectorResult:
        try:
            return await self.collect(address, chain)
        except Exception as e:
            if self.debug:
                self._debug_log.append({
                    "collector": self.name,
                    "label": "EXCEPTION",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                })
            return CollectorResult(source=self.name, success=False, error=str(e))

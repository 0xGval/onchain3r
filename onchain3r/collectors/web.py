"""Brave Search API collector."""

from __future__ import annotations

import os

from onchain3r.collectors.base import BaseCollector
from onchain3r.core.models import CollectorResult, WebData


class WebCollector(BaseCollector):
    name = "web"

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.api_key = os.getenv("BRAVE_SEARCH_API_KEY", "")
        self.base_url = config.get("brave", {}).get(
            "base_url", "https://api.search.brave.com/res/v1"
        )

    async def collect(self, address: str, chain: str) -> CollectorResult:
        if not self.api_key:
            return CollectorResult(
                source=self.name, success=False,
                error="BRAVE_SEARCH_API_KEY not set",
            )

        headers = {
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": self.api_key,
        }

        resp = await self.debug_request(
            "GET", f"{self.base_url}/web/search",
            headers=headers,
            params={"q": f"{address} token crypto", "count": "20"},
        )
        resp.raise_for_status()
        body = resp.json()

        results = body.get("web", {}).get("results", [])
        news = []
        audits = []
        website = None

        for r in results:
            title = r.get("title", "")
            url = r.get("url", "")
            desc = r.get("description", "")

            if "audit" in title.lower() or "audit" in desc.lower():
                audits.append(url)
            else:
                news.append({"title": title, "url": url, "snippet": desc})

            if not website and address.lower() not in url.lower():
                if any(kw in title.lower() for kw in ["official", "homepage"]):
                    website = url

        web_data = WebData(
            website=website,
            audit_reports=audits,
            news_mentions=news[:10],
        )
        return CollectorResult(source=self.name, success=True, data=web_data)

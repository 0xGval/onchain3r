"""Claude API integration for cross-reference analysis."""

from __future__ import annotations

import json
import os

import anthropic

from onchain3r.core.models import (
    CollectorResult,
    DueDiligenceReport,
    RiskCategory,
    RiskLevel,
    SocialData,
)

SYSTEM_PROMPT = """\
You are a crypto token due-diligence analyst. You receive structured data about a token \
from multiple sources (on-chain, DEX, social, web search). Your job is to cross-reference \
the data, identify red flags, and produce a risk assessment.

Respond ONLY with valid JSON matching this schema:
{
  "overall_risk_score": <1-10>,
  "overall_risk_level": "low"|"medium"|"high"|"critical",
  "overview": "<2-3 sentence overview>",
  "onchain_analysis": "<paragraph>",
  "social_analysis": "<paragraph>",
  "risk_categories": [
    {"name": "<category>", "score": <1-10>, "level": "low"|"medium"|"high"|"critical", "details": "<explanation>"}
  ],
  "risk_factors": ["<factor1>", ...],
  "positive_signals": ["<signal1>", ...],
  "verdict": "<final verdict paragraph>"
}

Risk categories to evaluate:
- Contract Risk (verified source, proxy, suspicious code patterns)
- Holder Concentration (top holders %, whale dominance)
- Deployer Risk (rug history, other tokens deployed)
- Liquidity Risk (low liquidity, unlocked, single pool)
- Social Risk (fake followers, no social presence, bot activity)
- Market Risk (low volume, extreme volatility, wash trading signals)

Launchpad context:
- If "launchpad" is present in onchain data with "known": true, it means the token was deployed \
via a known factory (e.g. Clanker). This is NEUTRAL information — not a positive signal, not a \
red flag. Anyone can deploy via these factories. Do NOT list it as a positive signal or green flag. \
Simply mention it as factual context (e.g. "Deployed via Clanker v4.0").
"""


class LLMAnalyzer:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.model = config.get("llm", {}).get("model", "claude-sonnet-4-20250514")
        self.max_tokens = config.get("llm", {}).get("max_tokens", 4096)
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    def analyze(
        self,
        address: str,
        chain: str,
        results: list[CollectorResult],
    ) -> DueDiligenceReport:
        # Build structured data payload for Claude (trimmed for token efficiency)
        data_payload: dict = {}
        for r in results:
            if r.data is not None:
                if isinstance(r.data, SocialData):
                    data_payload[r.source] = _trim_social(r.data)
                else:
                    data_payload[r.source] = r.data.model_dump(mode="json")
            else:
                data_payload[r.source] = {"error": r.error}

        user_msg = (
            f"Analyze this token for due diligence.\n"
            f"Token address: {address}\n"
            f"Chain: {chain}\n\n"
            f"Collected data:\n```json\n{json.dumps(data_payload, indent=2, default=str)}\n```"
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )

        text = response.content[0].text
        # Parse JSON from response (handle markdown code blocks)
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]

        parsed = json.loads(text.strip())

        return DueDiligenceReport(
            token_address=address,
            chain=chain,
            overall_risk_score=parsed["overall_risk_score"],
            overall_risk_level=RiskLevel(parsed["overall_risk_level"]),
            overview=parsed["overview"],
            onchain_analysis=parsed["onchain_analysis"],
            social_analysis=parsed["social_analysis"],
            risk_categories=[
                RiskCategory(**cat) for cat in parsed.get("risk_categories", [])
            ],
            risk_factors=parsed.get("risk_factors", []),
            positive_signals=parsed.get("positive_signals", []),
            verdict=parsed["verdict"],
            raw_data=data_payload,
        )


def _trim_social(data: SocialData) -> dict:
    """Produce a compact social summary for the LLM — no raw tweet lists."""
    trimmed: dict = {
        "twitter_mentions": data.twitter_mentions,
        "official_account": data.official_account,
        "follower_count": data.follower_count,
        "first_ca_poster": data.first_ca_poster,
        "has_discord": data.has_discord,
        "has_telegram": data.has_telegram,
    }
    if data.ticker_sentiment:
        trimmed["ticker_sentiment"] = data.ticker_sentiment.model_dump()
    if data.token_profile:
        trimmed["token_profile"] = data.token_profile.model_dump()
    if data.dev_accounts:
        trimmed["dev_accounts"] = [
            {"username": d.username, "followers": d.followers, "verified": d.verified}
            for d in data.dev_accounts
        ]
    if data.top_influencers_mentioning:
        trimmed["top_influencers_mentioning"] = [
            {"username": i.username, "followers": i.followers}
            for i in data.top_influencers_mentioning
        ]
    # Search summaries (counts only, no tweet text)
    trimmed["searches"] = [
        {"query_type": s.query_type, "tweet_count": s.tweet_count}
        for s in data.searches
    ]
    if data.linked_accounts:
        trimmed["linked_accounts"] = data.linked_accounts[:10]
    return trimmed

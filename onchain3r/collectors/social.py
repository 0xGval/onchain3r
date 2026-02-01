"""Twitter/X deep analysis via RapidAPI (twitter154).

Performs cascading searches:
1. Contract address
2. $TICKER / token name
3. Deployer address
4. Community search (discord/telegram detection)
5. Dev/project accounts found in tweets
6. User profile lookup for key accounts + token profile from DexScreener
"""

from __future__ import annotations

import os
import re

from onchain3r.collectors.base import BaseCollector
from onchain3r.core.models import (
    CollectorResult,
    SearchResult,
    SocialData,
    TickerSentiment,
    TweetData,
    TwitterUserInfo,
)

RAPIDAPI_HOST = "twitter154.p.rapidapi.com"
RAPIDAPI_BASE = f"https://{RAPIDAPI_HOST}"


class SocialCollector(BaseCollector):
    name = "social"

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.api_key = os.getenv("RAPIDAPI_KEY", "")
        # Context injected by engine from other collectors
        self.context: dict = {}

    def _headers(self) -> dict[str, str]:
        return {
            "x-rapidapi-key": self.api_key,
            "x-rapidapi-host": RAPIDAPI_HOST,
        }

    async def _search(self, query: str, section: str = "top", limit: int = 20) -> dict:
        resp = await self.debug_request(
            "GET",
            f"{RAPIDAPI_BASE}/search/search",
            headers=self._headers(),
            params={
                "query": query,
                "section": section,
                "min_retweets": "0",
                "min_likes": "0",
                "limit": str(limit),
                "language": "en",
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def _user_lookup(self, username: str) -> TwitterUserInfo | None:
        """Get user profile details."""
        try:
            resp = await self.debug_request(
                "GET",
                f"{RAPIDAPI_BASE}/user/details",
                headers=self._headers(),
                params={"username": username},
            )
            resp.raise_for_status()
            body = resp.json()
            # Handle nested response structure
            user = body if "user_id" in body else body.get("result", body)
            return TwitterUserInfo(
                username=user.get("username", username),
                name=user.get("name", ""),
                followers=user.get("follower_count", 0),
                following=user.get("following_count", 0),
                tweet_count=user.get("number_of_tweets", 0),
                created_at=user.get("creation_date", ""),
                verified=user.get("is_blue_verified", False),
                description=user.get("description", ""),
            )
        except Exception as e:
            self.log_debug("user_lookup_error", {"username": username, "error": str(e)})
            return None

    async def collect(self, address: str, chain: str) -> CollectorResult:
        import asyncio as _asyncio

        if not self.api_key:
            return CollectorResult(
                source=self.name, success=False,
                error="RAPIDAPI_KEY not set",
            )

        token_name = self.context.get("token_name")
        token_symbol = self.context.get("token_symbol")
        deployer = self.context.get("deployer_address")
        twitter_handle = self.context.get("twitter_handle")

        # --- Batch 1: All search queries in parallel ---
        search_tasks: list[tuple[str, str, int]] = [
            (address, "contract", 10),
        ]
        if token_symbol:
            search_tasks.append((f"${token_symbol}", "ticker", 20))
        if token_name and token_name.lower() != (token_symbol or "").lower():
            search_tasks.append((f"{token_name} crypto", "name", 10))
        if deployer:
            search_tasks.append((deployer, "deployer", 10))
        # Community search for discord/telegram links
        if token_name or token_symbol:
            community_q = f"{token_name or token_symbol} discord OR telegram OR community"
            search_tasks.append((community_q, "community", 10))

        search_results_raw = await _asyncio.gather(
            *[self._search(q, limit=lim) for q, _, lim in search_tasks]
        )

        all_searches: list[SearchResult] = []
        all_tweets: list[TweetData] = []
        for (query, qtype, _), body in zip(search_tasks, search_results_raw):
            sr = _parse_search(body, query, qtype)
            all_searches.append(sr)
            all_tweets.extend(sr.tweets)

        # --- Detect discord/telegram from community search tweets ---
        has_discord = False
        has_telegram = False
        for sr in all_searches:
            if sr.query_type == "community":
                for t in sr.tweets:
                    text_lower = t.text.lower()
                    if "discord.gg/" in text_lower or "discord.com/" in text_lower:
                        has_discord = True
                    if "t.me/" in text_lower or "telegram" in text_lower:
                        has_telegram = True

        # --- Compute ticker sentiment ---
        ticker_sentiment = None
        for sr in all_searches:
            if sr.query_type == "ticker" and sr.tweets:
                authors = {t.user for t in sr.tweets if t.user}
                total_likes = sum(t.likes for t in sr.tweets)
                total_rts = sum(t.retweets for t in sr.tweets)
                total_eng = total_likes + total_rts + sum(t.replies for t in sr.tweets)
                top = max(sr.tweets, key=lambda t: t.likes)
                ticker_sentiment = TickerSentiment(
                    total_tweets=sr.tweet_count,
                    unique_authors=len(authors),
                    total_likes=total_likes,
                    total_retweets=total_rts,
                    avg_engagement=total_eng / max(sr.tweet_count, 1),
                    is_organic=len(authors) > sr.tweet_count * 0.5,
                    top_tweet=top.text if top.likes > 0 else None,
                )
                break

        # --- First CA poster ---
        first_ca_poster = None
        for sr in all_searches:
            if sr.query_type == "contract" and sr.tweets:
                # Sort by created_at ascending (earliest first)
                sorted_tweets = sorted(
                    [t for t in sr.tweets if t.created_at],
                    key=lambda t: t.created_at,
                )
                if sorted_tweets:
                    first_ca_poster = sorted_tweets[0].user or None
                break

        # --- Extract linked accounts ---
        linked_accounts: set[str] = set()
        for t in all_tweets:
            for m in re.findall(r"@(\w{1,15})", t.text):
                linked_accounts.add(m.lower())

        # --- Identify dev/project candidates ---
        account_mention_count: dict[str, int] = {}
        for t in all_tweets:
            if t.user:
                account_mention_count[t.user] = account_mention_count.get(t.user, 0) + 1

        contract_tweeters = {
            t.user for t in all_tweets
            if t.query_source == "contract" and t.user
        }
        dev_candidates: list[str] = []
        for user, count in sorted(account_mention_count.items(), key=lambda x: -x[1]):
            if user in contract_tweeters or count >= 2:
                dev_candidates.append(user)
            if len(dev_candidates) >= 5:
                break

        # --- Batch 2: All user lookups in parallel ---
        influencer_candidates: list[str] = []
        seen: set[str] = set()
        for t in sorted(all_tweets, key=lambda t: t.user_followers, reverse=True):
            if t.user and t.user not in seen and t.user_followers > 1000:
                seen.add(t.user)
                influencer_candidates.append(t.user)
            if len(influencer_candidates) >= 3:
                break

        all_lookups = list(dict.fromkeys(dev_candidates[:5] + influencer_candidates))
        # Also lookup token profile from DexScreener twitter handle
        if twitter_handle and twitter_handle not in all_lookups:
            all_lookups.append(twitter_handle)

        lookup_results = await _asyncio.gather(
            *[self._user_lookup(u) for u in all_lookups]
        )
        lookup_map = {u: info for u, info in zip(all_lookups, lookup_results) if info}

        dev_accounts = [lookup_map[u] for u in dev_candidates[:5] if u in lookup_map]
        influencers = [lookup_map[u] for u in influencer_candidates if u in lookup_map]
        token_profile = lookup_map.get(twitter_handle) if twitter_handle else None

        # --- Batch 3: Dev account searches in parallel ---
        dev_search_tasks = []
        for dev in dev_accounts[:2]:
            if token_symbol:
                dev_search_tasks.append((f"from:{dev.username} ${token_symbol}", "dev_account", 5))

        if dev_search_tasks:
            dev_results = await _asyncio.gather(
                *[self._search(q, limit=lim) for q, _, lim in dev_search_tasks]
            )
            for (query, qtype, _), body in zip(dev_search_tasks, dev_results):
                all_searches.append(_parse_search(body, query, qtype))

        # --- Build result ---
        total_mentions = sum(s.tweet_count for s in all_searches)
        # Prefer DexScreener twitter handle as official account
        official = twitter_handle if token_profile else None
        if not official and dev_accounts:
            official = max(dev_accounts, key=lambda d: d.followers).username

        social = SocialData(
            twitter_mentions=total_mentions,
            ticker_sentiment=ticker_sentiment,
            official_account=official,
            token_profile=token_profile,
            follower_count=dev_accounts[0].followers if dev_accounts else None,
            account_age_days=None,
            first_ca_poster=first_ca_poster,
            has_discord=has_discord,
            has_telegram=has_telegram,
            searches=all_searches,
            dev_accounts=dev_accounts,
            top_influencers_mentioning=influencers,
            linked_accounts=sorted(linked_accounts)[:20],
        )
        return CollectorResult(source=self.name, success=True, data=social)


def _parse_search(body: dict, query: str, query_type: str) -> SearchResult:
    tweets: list[TweetData] = []
    results = body.get("results", [])
    for t in results:
        user_info = t.get("user", {})
        tweets.append(TweetData(
            text=t.get("full_text") or t.get("text", ""),
            user=user_info.get("username", ""),
            user_followers=user_info.get("follower_count", 0),
            likes=t.get("favorite_count", 0),
            retweets=t.get("retweet_count", 0),
            replies=t.get("reply_count", 0),
            created_at=t.get("creation_date", ""),
            query_source=query_type,
        ))
    return SearchResult(
        query=query,
        query_type=query_type,
        tweet_count=len(tweets),
        tweets=tweets,
    )

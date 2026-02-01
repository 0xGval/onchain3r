"""Twitter/X deep analysis via RapidAPI (twitter154).

Performs cascading searches:
1. Contract address
2. $TICKER / token name
3. Deployer address
4. Dev/project accounts found in tweets
5. User profile lookup for key accounts
"""

from __future__ import annotations

import os
import re

from onchain3r.collectors.base import BaseCollector
from onchain3r.core.models import (
    CollectorResult,
    SearchResult,
    SocialData,
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
        if not self.api_key:
            return CollectorResult(
                source=self.name, success=False,
                error="RAPIDAPI_KEY not set",
            )

        token_name = self.context.get("token_name")
        token_symbol = self.context.get("token_symbol")
        deployer = self.context.get("deployer_address")

        all_searches: list[SearchResult] = []
        all_tweets: list[TweetData] = []
        found_usernames: set[str] = set()

        # --- Phase 1: Search by contract address ---
        body = await self._search(address, limit=10)
        sr = _parse_search(body, address, "contract")
        all_searches.append(sr)
        all_tweets.extend(sr.tweets)
        for t in sr.tweets:
            if t.user:
                found_usernames.add(t.user)

        # --- Phase 2: Search by $TICKER ---
        if token_symbol:
            body = await self._search(f"${token_symbol}", limit=20)
            sr = _parse_search(body, f"${token_symbol}", "ticker")
            all_searches.append(sr)
            all_tweets.extend(sr.tweets)
            for t in sr.tweets:
                if t.user:
                    found_usernames.add(t.user)

        # --- Phase 3: Search by token name (if different from symbol) ---
        if token_name and token_name.lower() != (token_symbol or "").lower():
            body = await self._search(f"{token_name} crypto", limit=10)
            sr = _parse_search(body, f"{token_name} crypto", "name")
            all_searches.append(sr)
            all_tweets.extend(sr.tweets)

        # --- Phase 4: Search by deployer address ---
        if deployer:
            body = await self._search(deployer, limit=10)
            sr = _parse_search(body, deployer, "deployer")
            all_searches.append(sr)
            all_tweets.extend(sr.tweets)
            for t in sr.tweets:
                if t.user:
                    found_usernames.add(t.user)

        # --- Phase 5: Extract linked accounts from tweets ---
        # Find @mentions and URLs pointing to twitter profiles in tweet texts
        linked_accounts: set[str] = set()
        for t in all_tweets:
            mentions = re.findall(r"@(\w{1,15})", t.text)
            for m in mentions:
                linked_accounts.add(m.lower())

        # --- Phase 6: Identify dev/project accounts ---
        # Heuristic: accounts that tweeted about the contract address or are
        # frequently mentioned alongside the token
        dev_candidates: list[str] = []
        account_mention_count: dict[str, int] = {}
        for t in all_tweets:
            if t.user:
                account_mention_count[t.user] = account_mention_count.get(t.user, 0) + 1

        # Accounts appearing 2+ times or that tweeted the actual contract address
        contract_tweeters = {
            t.user for t in all_tweets
            if t.query_source == "contract" and t.user
        }
        for user, count in sorted(account_mention_count.items(), key=lambda x: -x[1]):
            if user in contract_tweeters or count >= 2:
                dev_candidates.append(user)
            if len(dev_candidates) >= 5:
                break

        # --- Phase 7: User profile lookups for key accounts ---
        dev_accounts: list[TwitterUserInfo] = []
        for username in dev_candidates[:5]:
            info = await self._user_lookup(username)
            if info:
                dev_accounts.append(info)

        # Also search for dev account names + token for more context
        for dev in dev_accounts[:2]:
            if token_symbol:
                body = await self._search(
                    f"from:{dev.username} ${token_symbol}", limit=5
                )
                sr = _parse_search(
                    body, f"from:{dev.username} ${token_symbol}", "dev_account"
                )
                all_searches.append(sr)

        # --- Phase 8: Top influencers mentioning the token ---
        influencers: list[TwitterUserInfo] = []
        top_by_followers = sorted(all_tweets, key=lambda t: t.user_followers, reverse=True)
        seen: set[str] = set()
        for t in top_by_followers:
            if t.user and t.user not in seen and t.user_followers > 1000:
                seen.add(t.user)
                info = await self._user_lookup(t.user)
                if info:
                    influencers.append(info)
            if len(influencers) >= 3:
                break

        # --- Build result ---
        total_mentions = sum(s.tweet_count for s in all_searches)

        # Find most likely official account
        official = None
        if dev_accounts:
            best = max(dev_accounts, key=lambda d: d.followers)
            official = best.username

        social = SocialData(
            twitter_mentions=total_mentions,
            official_account=official,
            follower_count=dev_accounts[0].followers if dev_accounts else None,
            account_age_days=None,
            sample_tweets=[t.text for t in all_tweets[:10]],
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

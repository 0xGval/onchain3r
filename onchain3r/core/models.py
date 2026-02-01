"""Pydantic models for token data, collector results, and reports."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TokenInfo(BaseModel):
    address: str
    chain: str
    name: str | None = None
    symbol: str | None = None
    decimals: int | None = None
    total_supply: str | None = None


class HolderInfo(BaseModel):
    address: str
    balance: str
    percentage: float
    label: str | None = None  # e.g. "PoolManager", "NonfungiblePositionManager"
    is_contract: bool = False


class LiquidityPool(BaseModel):
    pair_address: str
    dex: str
    token0: str
    token1: str
    liquidity_usd: float | None = None
    locked: bool | None = None
    lock_end: datetime | None = None


class DeployerInfo(BaseModel):
    address: str
    other_tokens_deployed: list[str] = Field(default_factory=list)
    known_rugs: list[str] = Field(default_factory=list)
    first_tx_date: datetime | None = None


class LaunchpadInfo(BaseModel):
    factory_address: str
    name: str | None = None
    known: bool = False
    creation_tx: str | None = None


class OnchainData(BaseModel):
    token: TokenInfo
    is_verified: bool = False
    is_proxy: bool = False
    implementation_address: str | None = None
    top_holders: list[HolderInfo] = Field(default_factory=list)
    holder_count: int | None = None
    deployer: DeployerInfo | None = None
    launchpad: LaunchpadInfo | None = None
    liquidity_pools: list[LiquidityPool] = Field(default_factory=list)
    source_code_snippet: str | None = None


class DexData(BaseModel):
    price_usd: float | None = None
    market_cap: float | None = None
    fdv: float | None = None
    volume_24h: float | None = None
    liquidity_usd: float | None = None
    price_change_24h: float | None = None
    price_change_1h: float | None = None
    pairs: list[dict[str, Any]] = Field(default_factory=list)
    dex_url: str | None = None


class TweetData(BaseModel):
    text: str
    user: str = ""
    user_followers: int = 0
    likes: int = 0
    retweets: int = 0
    replies: int = 0
    created_at: str = ""
    query_source: str = ""  # which search found this tweet


class TwitterUserInfo(BaseModel):
    username: str
    name: str = ""
    followers: int = 0
    following: int = 0
    tweet_count: int = 0
    created_at: str = ""
    verified: bool = False
    description: str = ""


class SearchResult(BaseModel):
    query: str
    query_type: str  # "contract", "ticker", "name", "deployer", "dev_account"
    tweet_count: int = 0
    tweets: list[TweetData] = Field(default_factory=list)


class SocialData(BaseModel):
    twitter_mentions: int = 0
    twitter_sentiment: str | None = None
    official_account: str | None = None
    follower_count: int | None = None
    account_age_days: int | None = None
    engagement_rate: float | None = None
    sample_tweets: list[str] = Field(default_factory=list)
    # Deep analysis fields
    searches: list[SearchResult] = Field(default_factory=list)
    dev_accounts: list[TwitterUserInfo] = Field(default_factory=list)
    top_influencers_mentioning: list[TwitterUserInfo] = Field(default_factory=list)
    linked_accounts: list[str] = Field(default_factory=list)


class WebData(BaseModel):
    website: str | None = None
    audit_reports: list[str] = Field(default_factory=list)
    news_mentions: list[dict[str, str]] = Field(default_factory=list)
    forum_mentions: list[dict[str, str]] = Field(default_factory=list)


class CollectorResult(BaseModel):
    source: str
    success: bool
    error: str | None = None
    data: OnchainData | DexData | SocialData | WebData | None = None


class RiskCategory(BaseModel):
    name: str
    score: int = Field(ge=1, le=10)
    level: RiskLevel
    details: str


class DueDiligenceReport(BaseModel):
    token_address: str
    chain: str
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    overall_risk_score: int = Field(ge=1, le=10)
    overall_risk_level: RiskLevel
    overview: str
    onchain_analysis: str
    social_analysis: str
    risk_categories: list[RiskCategory] = Field(default_factory=list)
    risk_factors: list[str] = Field(default_factory=list)
    positive_signals: list[str] = Field(default_factory=list)
    verdict: str
    raw_data: dict[str, Any] = Field(default_factory=dict)

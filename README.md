# onchain3r

Automated token due diligence engine for EVM chains. Aggregates on-chain, DEX, social, and web intelligence, then synthesizes a risk assessment via LLM cross-referencing.

Built for Base. Other EVM chains coming soon.

<img width="1229" height="1284" alt="image" src="https://github.com/user-attachments/assets/126bac6e-b47f-45ac-a982-4eb6e77338b3" />

---

## How it works

```
Token Address
     |
     v
 +-------------------+     +-------------------+
 | DexScreener pre-  |     | RPC token info    |
 | fetch (price,     |     | (name, symbol,    |
 | twitter handle)   |     |  supply)          |
 +--------+----------+     +--------+----------+
          |                          |
          +--------> context <-------+
                       |
    +------------------+------------------+
    |                  |                  |
    v                  v                  v
 On-chain           Social             Web
 collector          collector          collector
    |                  |                  |
    |  - Source code   |  - CA search     |  - News
    |  - Holders +     |  - $TICKER       |  - Audits
    |    labels        |    sentiment     |  - Forums
    |  - Deployer      |  - Community     |
    |  - Launchpad     |    (discord/tg)  |
    |    detection     |  - Dev accounts  |
    |                  |  - Influencers   |
    |                  |  - Token profile |
    |                  |  - First CA      |
    |                  |    poster        |
    +------------------+------------------+
                       |
                       v
              LLM Risk Analysis
              (Claude cross-ref)
                       |
                       v
              Risk Report (1-10)
              6 scored categories
              + verdict
```

## Features

### On-chain intelligence
- Contract source verification and proxy detection via Etherscan V2
- Top 20 holder analysis with **contract labeling** via Blockscout (PoolManager, SafeProxy, Vesting contracts, etc.)
- Deployer identification with Routescan fallback for free-plan compatibility
- **Launchpad detection** -- matches deployer against known factory registry (Clanker v3/v4, extensible)

### DEX data
- Real-time price, market cap, FDV, volume, liquidity from DexScreener
- Multi-pair discovery (up to 10 pairs)
- Twitter handle extraction from DexScreener social links

### Social / X analysis
- Multi-query parallel search: contract address, $TICKER, token name, deployer, community
- **Ticker sentiment aggregation**: unique authors, engagement rate, organic vs bot detection
- **First CA poster** detection (who posted the contract address first)
- **Token profile** lookup from DexScreener twitter handle
- Dev/project account identification and profile enrichment
- Top influencer detection (follower count, verified status)
- Community presence detection (Discord, Telegram links in tweets)
- Data trimming for LLM -- sends aggregated metrics, not raw tweet dumps

### Web intelligence
- News mentions via Brave Search
- Audit report detection
- Forum/community mentions

### LLM risk engine
- Claude-powered cross-reference analysis across all data sources
- 6 scored risk categories (1-10): Contract, Holder Concentration, Deployer, Liquidity, Social, Market
- Launchpad context treated as **neutral signal** (not green flag, not red flag)
- Structured JSON output with risk factors, positive signals, and verdict

### Frontend
- Dark theme UI with Base chain aesthetic
- Real-time progress via WebSocket
- Risk score ring with color-coded categories
- **Quick links** to Basescan, DexScreener, official Twitter, dev/influencer profiles
- Two-column responsive layout
- Chain selector (Base active, others greyed out as coming soon)

---

## Quick start

```bash
git clone https://github.com/0xGval/onchain3r.git
cd onchain3r
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -e .
cp .env.example .env
```

Edit `.env` with your API keys, then:

```bash
# CLI -- full analysis
onchain3r analyze 0x9f86dB9fc6f7c9408e8Fda3Ff8ce4e78ac7a6b07 --chain base

# CLI -- debug a specific collector
onchain3r debug 0x9f86dB9fc6f7c9408e8Fda3Ff8ce4e78ac7a6b07 --chain base --collector social

# Web UI
uvicorn onchain3r.api:app --reload
# Open http://localhost:8000
```

---

## API keys

| Key | Source | Required |
|-----|--------|----------|
| `ANTHROPIC_API_KEY` | [Anthropic](https://console.anthropic.com/) | Yes |
| `BASESCAN_API_KEY` | [Etherscan V2](https://etherscan.io/apis) | Yes |
| `RAPIDAPI_KEY` | [RapidAPI - twitter154](https://rapidapi.com/davethebeast/api/twitter154) | For social analysis |
| `BRAVE_SEARCH_API_KEY` | [Brave Search](https://brave.com/search/api/) | For web analysis |
| `BASE_RPC_URL` | Any Base RPC (Alchemy, Infura, etc.) | Optional (defaults to public RPC) |

---

## Project structure

```
onchain3r/
  core/
    engine.py          # Orchestrator -- coordinates collectors + LLM
    models.py          # Pydantic models (TokenInfo, SocialData, DueDiligenceReport, etc.)
  collectors/
    base.py            # Base collector with HTTP client + debug logging
    onchain.py         # Etherscan V2 + Routescan + Blockscout + RPC
    dex.py             # DexScreener API
    social.py          # Twitter/X via RapidAPI (twitter154)
    web.py             # Brave Search API
  analyzer/
    llm.py             # Claude integration + social data trimming
  reporter/
    generator.py       # Markdown report formatter
  api.py               # FastAPI + WebSocket server
  cli.py               # Typer CLI
frontend/
  index.html           # Single-file frontend (no build step)
config.yaml            # Chain config + launchpad factory registry
```

---

## Supported chains

| Chain | Status |
|-------|--------|
| Base | Full support |
| Ethereum | Partial (on-chain + DEX) |
| Arbitrum | Planned |
| Optimism | Planned |

---

## Performance

All collectors run in parallel with internal call parallelization:

- On-chain collector: 4 parallel calls (token info, source code, holders, deployer) + parallel Blockscout labeling
- Social collector: 3-batch parallel pattern (searches -> lookups -> dev searches)
- DexScreener pre-fetched alongside RPC token info
- Typical full analysis: ~30-40s (bottleneck: social API rate limits + LLM inference)

---

## License

MIT

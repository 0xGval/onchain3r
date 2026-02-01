# onchain3r

Automated token due diligence system for EVM chains. Collects on-chain, DEX, social, and web data, then produces a risk assessment report using LLM analysis.

## Features

- **On-chain analysis**: contract verification, holder concentration with contract labeling (pools, vesting, multisigs), deployer history
- **Launchpad detection**: identifies tokens deployed via known factories (Clanker v3/v4, etc.)
- **DEX data**: price, liquidity, volume, pairs via DexScreener
- **Social intelligence**: Twitter mentions, bot detection, coordinated promotion patterns
- **Web search**: news, audits, forum mentions via Brave Search
- **LLM risk report**: cross-references all data sources into a scored risk assessment

## Setup

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e .
cp .env.example .env
# Fill in your API keys in .env
```

### Required API keys

| Key | Source | Required |
|-----|--------|----------|
| `ANTHROPIC_API_KEY` | [Anthropic](https://console.anthropic.com/) | Yes |
| `BASESCAN_API_KEY` | [Etherscan](https://etherscan.io/apis) | Yes |
| `BRAVE_SEARCH_API_KEY` | [Brave Search](https://brave.com/search/api/) | For web collector |
| `RAPIDAPI_KEY` | [RapidAPI](https://rapidapi.com/) | For social collector |
| `BASE_RPC_URL` | Any Base RPC provider | Optional (defaults to public RPC) |

## Usage

```bash
# Full analysis
onchain3r analyze <token_address> --chain base

# Debug specific collector
onchain3r debug <token_address> --chain base --collector onchain
```

## Architecture

```
Phase 1 (parallel): onchain + dex + web collectors
    |
    +-- Launchpad detection (matches deployer vs known factory registry)
    +-- Holder labeling (Blockscout: pools, vesting, multisigs)
    +-- Routescan fallback for Etherscan free plan limitations
    |
Phase 2 (with context): social collector
    |
LLM Analysis -> Risk Report
```

## Supported chains

- Base (primary)
- Ethereum, Arbitrum, Optimism (partial)

## License

MIT

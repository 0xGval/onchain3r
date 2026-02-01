"""On-chain data collector via Etherscan V2 API and Base RPC."""

from __future__ import annotations

import os

from onchain3r.collectors.base import BaseCollector
from onchain3r.core.models import (
    CollectorResult,
    DeployerInfo,
    HolderInfo,
    LaunchpadInfo,
    OnchainData,
    TokenInfo,
)

ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
]

# Etherscan V2 unified endpoint
ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"

# Routescan fallback (free, supports Base)
ROUTESCAN_V2 = "https://api.routescan.io/v2/network/mainnet/evm/{chain_id}/etherscan/api"

# Blockscout API (free, for address labeling)
BLOCKSCOUT_URLS = {
    "base": "https://base.blockscout.com/api/v2",
    "ethereum": "https://eth.blockscout.com/api/v2",
}

# Chain IDs
CHAIN_IDS = {
    "base": "8453",
    "ethereum": "1",
    "arbitrum": "42161",
    "optimism": "10",
}


class OnchainCollector(BaseCollector):
    name = "onchain"

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.api_key = os.getenv("BASESCAN_API_KEY", "")
        self.rpc_url = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        self._token_info_cache: dict[str, TokenInfo] = {}

    async def _explorer_get(self, chain: str, **params: str) -> dict:
        params["apikey"] = self.api_key
        params["chainid"] = CHAIN_IDS.get(chain, "8453")
        resp = await self.debug_request("GET", ETHERSCAN_V2, params=params)
        resp.raise_for_status()
        return resp.json()

    async def _get_token_info(self, address: str) -> TokenInfo:
        if address in self._token_info_cache:
            return self._token_info_cache[address]
        from web3 import AsyncWeb3
        from web3.providers import AsyncHTTPProvider

        w3 = AsyncWeb3(AsyncHTTPProvider(self.rpc_url))
        contract = w3.eth.contract(
            address=AsyncWeb3.to_checksum_address(address), abi=ERC20_ABI
        )
        try:
            name = await contract.functions.name().call()
        except Exception:
            name = None
        try:
            symbol = await contract.functions.symbol().call()
        except Exception:
            symbol = None
        try:
            decimals = await contract.functions.decimals().call()
        except Exception:
            decimals = None
        try:
            total_supply = str(await contract.functions.totalSupply().call())
        except Exception:
            total_supply = None

        info = TokenInfo(
            address=address, chain="base", name=name, symbol=symbol,
            decimals=decimals, total_supply=total_supply,
        )
        self._token_info_cache[address] = info
        return info

    async def _get_source_code(self, address: str, chain: str) -> tuple[bool, bool, str | None, str | None]:
        data = await self._explorer_get(
            chain, module="contract", action="getsourcecode", address=address
        )
        results = data.get("result", [])
        if not results or isinstance(results, str):
            return False, False, None, None
        r = results[0]
        if isinstance(r, str):
            return False, False, None, None
        is_verified = r.get("SourceCode", "") != ""
        is_proxy = r.get("Proxy") == "1"
        impl = r.get("Implementation") or None
        source = r.get("SourceCode", "")
        snippet = source[:2000] if source else None
        return is_verified, is_proxy, impl, snippet

    async def _get_top_holders(self, address: str, chain: str) -> list[HolderInfo]:
        result = []

        # Routescan first (free, reliable for Base)
        chain_id = CHAIN_IDS.get(chain, "8453")
        url = ROUTESCAN_V2.format(chain_id=chain_id)
        try:
            resp = await self.debug_request(
                "GET", url,
                params={"module": "token", "action": "tokenholderlist",
                        "contractaddress": address, "page": "1", "offset": "20"},
            )
            resp.raise_for_status()
            result = resp.json().get("result", [])
        except Exception:
            pass

        # Fallback: Etherscan V2
        if not result or isinstance(result, str):
            data = await self._explorer_get(
                chain, module="token", action="tokenholderlist",
                contractaddress=address, page="1", offset="20",
            )
            result = data.get("result", [])

        holders = []
        if not result or isinstance(result, str):
            return holders
        for h in result:
            if isinstance(h, dict):
                holders.append(HolderInfo(
                    address=h.get("TokenHolderAddress", ""),
                    balance=h.get("TokenHolderQuantity", "0"),
                    percentage=0.0,
                ))

        # Label holders via Blockscout (identify contracts like pools, routers)
        await self._label_holders(holders, chain)
        return holders

    async def _label_holders(self, holders: list[HolderInfo], chain: str) -> None:
        """Label holder addresses using Blockscout to identify contracts."""
        import asyncio as _asyncio

        base_url = BLOCKSCOUT_URLS.get(chain)
        if not base_url:
            return

        async def _label_one(holder: HolderInfo) -> None:
            try:
                resp = await self.debug_request(
                    "GET", f"{base_url}/addresses/{holder.address}",
                )
                if resp.status_code == 200:
                    data = resp.json()
                    holder.is_contract = data.get("is_contract", False)
                    name = data.get("name")
                    if name:
                        holder.label = name
            except Exception:
                pass

        await _asyncio.gather(*[_label_one(h) for h in holders])

    async def _get_contract_creation(self, address: str, chain: str) -> dict | None:
        """Get contract creation info. Routescan first (free), Etherscan V2 fallback."""
        # Routescan first — free and reliable for Base
        chain_id = CHAIN_IDS.get(chain, "8453")
        url = ROUTESCAN_V2.format(chain_id=chain_id)
        try:
            resp = await self.debug_request(
                "GET", url,
                params={"module": "contract", "action": "getcontractcreation",
                        "contractaddresses": address},
            )
            resp.raise_for_status()
            results = resp.json().get("result", [])
            if results and not isinstance(results, str) and isinstance(results[0], dict):
                return results[0]
        except Exception:
            pass

        # Fallback: Etherscan V2
        data = await self._explorer_get(
            chain, module="contract", action="getcontractcreation",
            contractaddresses=address,
        )
        results = data.get("result", [])
        if results and not isinstance(results, str) and isinstance(results[0], dict):
            return results[0]
        return None

    async def _get_deployer(self, address: str, chain: str) -> DeployerInfo | None:
        creation = await self._get_contract_creation(address, chain)
        if not creation:
            return None
        deployer_addr = creation.get("contractCreator", "")
        return DeployerInfo(address=deployer_addr)

    def _match_launchpad(self, deployer_address: str, chain: str) -> LaunchpadInfo | None:
        """Match deployer address against known factory/launchpad registry."""
        if not deployer_address:
            return None
        registry = self.config.get("launchpads", {}).get(chain, [])
        for entry in registry:
            if entry["address"].lower() == deployer_address.lower():
                return LaunchpadInfo(
                    factory_address=deployer_address,
                    name=entry["name"],
                    known=True,
                )
        return LaunchpadInfo(factory_address=deployer_address, known=False)

    async def collect(self, address: str, chain: str) -> CollectorResult:
        import asyncio as _asyncio

        # Run all independent calls in parallel
        token_info_t, source_t, holders_t, deployer_t = await _asyncio.gather(
            self._get_token_info(address),
            self._get_source_code(address, chain),
            self._get_top_holders(address, chain),
            self._get_deployer(address, chain),
        )

        token_info = token_info_t
        is_verified, is_proxy, impl, snippet = source_t
        top_holders = holders_t
        deployer = deployer_t
        launchpad = self._match_launchpad(
            deployer.address if deployer else "", chain
        )

        onchain = OnchainData(
            token=token_info,
            is_verified=is_verified,
            is_proxy=is_proxy,
            implementation_address=impl,
            top_holders=top_holders,
            deployer=deployer,
            launchpad=launchpad,
            source_code_snippet=snippet,
        )
        return CollectorResult(source=self.name, success=True, data=onchain)

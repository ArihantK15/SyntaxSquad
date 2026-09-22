import threading
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from eth_account import Account
from web3 import Web3

from app.core.config import settings


class AnchorConfigurationError(Exception):
    """Raised when anchoring is attempted without a configured wallet key."""


class BaseBlockchainAnchorService(ABC):
    @abstractmethod
    def anchor(self, head_hash: str) -> Dict[str, Any]:
        """Publishes `head_hash` to a public testnet and returns tx details."""
        pass


# Only one anchor transaction should ever be in flight at a time. This is a
# rare, deliberate officer action (never called from AuditService's hot
# path -- see that module), not a high-throughput operation, so a simple
# process-wide lock is enough to stop two nearly-simultaneous requests (e.g.
# a double-click) from fetching the same pending nonce and racing each other.
_ANCHOR_LOCK = threading.Lock()


class Web3BlockchainAnchorService(BaseBlockchainAnchorService):
    """
    Anchors the audit ledger's head hash (see AuditService -- it already
    commits to the FULL chain history by construction, since each entry_hash
    embeds the previous one, so anchoring it is equivalent to anchoring a
    Merkle root) to a public EVM testnet (configured via settings.ANCHOR_*;
    Ethereum Sepolia by default) by sending a zero-value transaction to the
    wallet's own address with the hash as raw calldata.

    Deliberately no smart contract: an EVM transaction's data field can hold
    arbitrary bytes, and a plain, publicly-verifiable, immutably-timestamped
    transaction is all a "this hash existed at time T" claim needs -- the
    same pattern OpenTimestamps/proof-of-existence services use. A judge (or
    anyone) can independently confirm it on a block explorer without
    trusting this application's database at all.
    """

    # 21000 base + up to 32 bytes of non-zero calldata at 16 gas/byte (512)
    # for a bytes32 payload, plus headroom -- unused gas is refunded, so a
    # conservative constant here costs nothing and avoids an extra
    # eth_estimateGas round-trip (and its own failure mode) for a fixed,
    # known-shape transaction.
    GAS_LIMIT = 30_000

    def __init__(self, w3: Optional[Web3] = None):
        if not settings.ANCHOR_PRIVATE_KEY:
            raise AnchorConfigurationError(
                "ANCHOR_PRIVATE_KEY is not configured -- blockchain anchoring is "
                "disabled. Set it to a throwaway testnet wallet's private key "
                "(never a wallet holding anything of real value) to enable this "
                "feature."
            )
        self.w3 = w3 if w3 is not None else Web3(Web3.HTTPProvider(settings.ANCHOR_RPC_URL))
        self.account = Account.from_key(settings.ANCHOR_PRIVATE_KEY)

    def _build_transaction(self, head_hash: str) -> Dict[str, Any]:
        """Pure(ish) transaction-shape construction, factored out from
        signing/sending so the exact calldata/fields can be asserted on
        directly in tests without needing to decode a signed, RLP-encoded
        transaction."""
        return {
            "from": self.account.address,
            "to": self.account.address,
            "value": 0,
            "data": "0x" + head_hash,
            "nonce": self.w3.eth.get_transaction_count(self.account.address, "pending"),
            "gas": self.GAS_LIMIT,
            "gasPrice": self.w3.eth.gas_price,
            "chainId": settings.ANCHOR_CHAIN_ID,
        }

    def anchor(self, head_hash: str) -> Dict[str, Any]:
        with _ANCHOR_LOCK:
            tx = self._build_transaction(head_hash)
            signed = self.account.sign_transaction(tx)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            # Waited for synchronously (bounded timeout) rather than fired
            # and forgotten -- an officer triggering this on demand wants to
            # know it actually landed on-chain, not just that it was
            # broadcast, and a testnet's short block time makes this a brief
            # wait in practice.
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

            tx_hash_hex = tx_hash.hex() if hasattr(tx_hash, "hex") else str(tx_hash)
            if not tx_hash_hex.startswith("0x"):
                tx_hash_hex = "0x" + tx_hash_hex

            return {
                "tx_hash": tx_hash_hex,
                "network": settings.ANCHOR_NETWORK_NAME,
                "chain_id": settings.ANCHOR_CHAIN_ID,
                "block_number": receipt.blockNumber,
                "explorer_url": f"{settings.ANCHOR_EXPLORER_TX_URL}{tx_hash_hex}",
            }


def get_blockchain_anchor_service() -> BaseBlockchainAnchorService:
    return Web3BlockchainAnchorService()

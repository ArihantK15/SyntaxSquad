from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.blockchain_anchor_service import (
    AnchorConfigurationError,
    Web3BlockchainAnchorService,
    get_blockchain_anchor_service,
)

TEST_PRIVATE_KEY = "0x" + "11" * 32  # syntactically valid, holds no real value
TEST_ADDRESS_HEAD_HASH = "a" * 64  # a plausible SHA-256 hex digest


def _fake_w3(tx_hash_bytes=b"\xab" * 32, block_number=12345, nonce=7, gas_price=30_000_000_000):
    """A stand-in for web3.py's Web3 client -- only the .eth surface the
    service actually touches is faked, so no real network call ever happens
    in this test file (the mandatory "mock the chain call for CI" half of
    this feature's test plan; the real-network half is a manual one-off
    run, never part of the automated suite)."""
    eth = MagicMock()
    eth.get_transaction_count.return_value = nonce
    eth.gas_price = gas_price
    eth.send_raw_transaction.return_value = tx_hash_bytes
    eth.wait_for_transaction_receipt.return_value = SimpleNamespace(blockNumber=block_number, status=1)
    return SimpleNamespace(eth=eth)


def test_raises_clear_error_when_not_configured(monkeypatch):
    """Absent a configured wallet key, the service must refuse to construct
    rather than silently failing on first anchor() call -- and it must never
    be reachable at all from AuditService's own hot path (see that module),
    so this failure mode only ever surfaces to an officer explicitly
    triggering the on-demand anchor action."""
    monkeypatch.setattr("app.services.blockchain_anchor_service.settings.ANCHOR_PRIVATE_KEY", "")
    with pytest.raises(AnchorConfigurationError):
        Web3BlockchainAnchorService()


def test_build_transaction_carries_the_real_head_hash_as_calldata(monkeypatch):
    """The entire point of this feature is that the exact bytes published
    on-chain ARE the audit ledger's real head hash -- pin this down
    precisely rather than trusting the orchestration method's return value
    alone."""
    monkeypatch.setattr("app.services.blockchain_anchor_service.settings.ANCHOR_PRIVATE_KEY", TEST_PRIVATE_KEY)
    monkeypatch.setattr("app.services.blockchain_anchor_service.settings.ANCHOR_CHAIN_ID", 11155111)
    svc = Web3BlockchainAnchorService(w3=_fake_w3())

    tx = svc._build_transaction(TEST_ADDRESS_HEAD_HASH)

    assert tx["data"] == "0x" + TEST_ADDRESS_HEAD_HASH
    assert tx["to"] == svc.account.address
    assert tx["from"] == svc.account.address
    assert tx["value"] == 0
    assert tx["chainId"] == 11155111
    assert tx["nonce"] == 7
    assert tx["gasPrice"] == 30_000_000_000


def test_anchor_returns_tx_details_and_waits_for_confirmation(monkeypatch):
    monkeypatch.setattr("app.services.blockchain_anchor_service.settings.ANCHOR_PRIVATE_KEY", TEST_PRIVATE_KEY)
    monkeypatch.setattr("app.services.blockchain_anchor_service.settings.ANCHOR_CHAIN_ID", 11155111)
    monkeypatch.setattr("app.services.blockchain_anchor_service.settings.ANCHOR_NETWORK_NAME", "Ethereum Sepolia")
    monkeypatch.setattr("app.services.blockchain_anchor_service.settings.ANCHOR_EXPLORER_TX_URL", "https://sepolia.etherscan.io/tx/")
    fake_w3 = _fake_w3(tx_hash_bytes=b"\xab" * 32, block_number=12345)
    svc = Web3BlockchainAnchorService(w3=fake_w3)

    result = svc.anchor(TEST_ADDRESS_HEAD_HASH)

    expected_tx_hash = "0x" + ("ab" * 32)
    assert result["tx_hash"] == expected_tx_hash
    assert result["network"] == "Ethereum Sepolia"
    assert result["chain_id"] == 11155111
    assert result["block_number"] == 12345
    assert result["explorer_url"] == f"https://sepolia.etherscan.io/tx/{expected_tx_hash}"

    # Must actually wait for on-chain confirmation, not just fire-and-forget --
    # an officer triggering this wants to know it landed, not just that it
    # was broadcast.
    fake_w3.eth.wait_for_transaction_receipt.assert_called_once()
    fake_w3.eth.send_raw_transaction.assert_called_once()


def test_anchor_only_ever_sends_the_hash_given_to_it(monkeypatch):
    """Regression guard against a copy-paste/stale-state bug: two different
    head hashes must produce two transactions with two different calldata
    payloads, not the same one reused."""
    monkeypatch.setattr("app.services.blockchain_anchor_service.settings.ANCHOR_PRIVATE_KEY", TEST_PRIVATE_KEY)
    svc = Web3BlockchainAnchorService(w3=_fake_w3())

    tx_a = svc._build_transaction("a" * 64)
    tx_b = svc._build_transaction("b" * 64)

    assert tx_a["data"] != tx_b["data"]
    assert tx_a["data"] == "0x" + "a" * 64
    assert tx_b["data"] == "0x" + "b" * 64


def test_factory_returns_real_service_when_configured(monkeypatch):
    monkeypatch.setattr("app.services.blockchain_anchor_service.settings.ANCHOR_PRIVATE_KEY", TEST_PRIVATE_KEY)
    svc = get_blockchain_anchor_service()
    assert isinstance(svc, Web3BlockchainAnchorService)

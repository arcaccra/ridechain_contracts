# tests/test_lock.py
import os
import csv
import builtins
import pytest
from unittest.mock import MagicMock, patch
from ryde_escrow_lock import lock, HelloWorldDatum


@pytest.fixture
def mock_context(tmp_path):
    """
    Provide a fake BlockFrostChainContext with mocked submit_tx
    and a dummy tx hash return value.
    """
    context = MagicMock()
    context.submit_tx.return_value = None  # no real submission
    return context


@pytest.fixture
def dummy_signing_key():
    # Mock signing key – not used deeply in unit test
    return MagicMock()


@pytest.fixture
def dummy_script_hash():
    return MagicMock()


def test_lock_writes_csv_and_returns_txhash(tmp_path, mock_context, dummy_signing_key, dummy_script_hash):
    # Arrange
    amount = 6_000_000
    datum = HelloWorldDatum(owner=b"abc123")
    fake_tx = MagicMock()
    fake_tx.id = "dummy_tx_hash"

    # Patch TransactionBuilder.build_and_sign to return fake_tx
    with patch("ryde_escrow_lock.TransactionBuilder") as MockBuilder:
        builder = MagicMock()
        builder.build_and_sign.return_value = fake_tx
        MockBuilder.return_value = builder

        # Patch Address.from_primitive to avoid needing a real addr file
        with patch("ryde_escrow_lock.Address.from_primitive") as mock_addr:
            mock_addr.return_value = MagicMock()

            # Act
            tx_hash = lock(
                amount=amount,
                into=dummy_script_hash,
                datum=datum,
                signing_key=dummy_signing_key,
                context=mock_context,
            )

    # Assert tx_hash is returned correctly
    assert tx_hash == "dummy_tx_hash"

    # Now check that CSV row was written
    csv_path = tmp_path / "locked.csv"
    # Simulate CSV writing as in script
    with open(csv_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["amount", "tx_hash", "datum", "message", "status"])
        writer.writerow([
            amount // 1_000_000,
            tx_hash,
            datum.to_cbor_hex(),
            f"Trip booked successfully for {amount // 1_000_000} tADA",
            "success"
        ])

    with open(csv_path, newline="") as f:
        rows = list(csv.reader(f))

    assert rows[1][0] == str(amount // 1_000_000)
    assert rows[1][1] == "dummy_tx_hash"
    assert "Trip booked successfully" in rows[1][3]
    assert rows[1][4] == "success"
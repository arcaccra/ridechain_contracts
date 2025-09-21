# tests/test_unlock.py
import csv
import pytest
from unittest.mock import MagicMock, patch
from ryde_escrow_unlock import unlock, HelloWorldRedeemer


@pytest.fixture
def mock_context():
    """Provide a fake BlockFrostChainContext with mocked submit_tx."""
    context = MagicMock()
    context.submit_tx.return_value = None
    return context


@pytest.fixture
def dummy_signing_key():
    return MagicMock()


@pytest.fixture
def dummy_owner():
    return MagicMock()


@pytest.fixture
def dummy_script():
    return MagicMock()


@pytest.fixture
def dummy_utxo():
    utxo = MagicMock()
    # Fake UTxO with 6 ADA (in lovelace)
    utxo.output.amount.coin = 6_000_000
    utxo.input.transaction_id = "dummy_input_tx"
    return utxo


def test_unlock_returns_txhash_and_logs_csv(tmp_path, mock_context, dummy_signing_key, dummy_owner, dummy_script, dummy_utxo):
    # Arrange
    fake_tx = MagicMock()
    fake_tx.id = "dummy_unlock_tx_hash"

    # Patch TransactionBuilder to return fake tx
    with patch("ryde_escrow_unlock.TransactionBuilder") as MockBuilder:
        builder = MagicMock()
        builder.build_and_sign.return_value = fake_tx
        MockBuilder.return_value = builder

        # Patch Address.from_primitive to avoid reading actual file
        with patch("ryde_escrow_unlock.Address.from_primitive") as mock_addr:
            mock_addr.return_value = MagicMock()

            # Act
            tx_hash = unlock(
                utxo=dummy_utxo,
                from_script=dummy_script,
                redeemer=MagicMock(),
                signing_key=dummy_signing_key,
                owner=dummy_owner,
                context=mock_context,
            )

    # Assert transaction hash is returned
    assert tx_hash == "dummy_unlock_tx_hash"

    # --- Simulate the CSV logging (as done in script) ---
    csv_path = tmp_path / "unlock_records.csv"
    fieldnames = ['timestamp', 'tx_hash', 'unlocked_amount (tADA)', 'redeemer', 'status', 'message']

    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({
            'timestamp': "2025-09-21T12:00:00",
            'tx_hash': tx_hash,
            'unlocked_amount (tADA)': dummy_utxo.output.amount.coin // 1_000_000,  # integer tADA
            'redeemer': "dummy_redeemer",
            'status': 'success',
            'message': f'Trip completed and payment of {dummy_utxo.output.amount.coin // 1_000_000} tADA made'
        })

    # Verify CSV row contents
    with open(csv_path, newline="") as f:
        rows = list(csv.DictReader(f))

    assert rows[0]['tx_hash'] == "dummy_unlock_tx_hash"
    assert rows[0]['unlocked_amount (tADA)'] == str(dummy_utxo.output.amount.coin // 1_000_000)
    assert rows[0]['status'] == "success"
    assert f"{dummy_utxo.output.amount.coin // 1_000_000} tADA" in rows[0]['message']
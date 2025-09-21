from dataclasses import dataclass

from humanfriendly.terminal import message
from pycardano import (
    Address,
    BlockFrostChainContext,
    Network,
    PaymentSigningKey,
    PaymentVerificationKey,
    PlutusData,
    PlutusV3Script,
    Redeemer,
    ScriptHash,
    TransactionBuilder,
    TransactionOutput,
    UTxO,
)
from pycardano.hash import (
    VerificationKeyHash,
    TransactionId,
    ScriptHash,
)
import json
import os
import sys
import csv
import environ

# set env for environ to read .env file
environ.Env.read_env()
env = environ.Env()

def read_validator() -> dict:
    with open("plutus.json", "r") as f:
        validator = json.load(f)
    script_bytes = PlutusV3Script(
        bytes.fromhex(validator["validators"][0]["compiledCode"])
    )
    script_hash = ScriptHash(bytes.fromhex(validator["validators"][0]["hash"]))
    return {
        "type": "PlutusV3",
        "script_bytes": script_bytes,
        "script_hash": script_hash,
    }


def unlock(
        utxo: UTxO,
        from_script: PlutusV3Script,
        redeemer: Redeemer,
        signing_key: PaymentSigningKey,
        owner: VerificationKeyHash,
        context: BlockFrostChainContext,
) -> TransactionId:
    # read addresses
    with open("me.addr", "r") as f:
        input_address = Address.from_primitive(f.read())

    # build transaction
    builder = TransactionBuilder(context=context)
    builder.add_script_input(
        utxo=utxo,
        script=from_script,
        redeemer=redeemer,
    )
    builder.add_input_address(input_address)
    builder.add_output(
        TransactionOutput(
            address=input_address,
            amount=utxo.output.amount.coin,
        )
    )
    builder.required_signers = [owner]
    signed_tx = builder.build_and_sign(
        signing_keys=[signing_key],
        change_address=input_address,
    )

    # submit transaction
    context.submit_tx(signed_tx)
    return signed_tx.id


def get_utxo_from_str(context, tx_id: str, contract_address: Address) -> UTxO:
    for utxo in context.utxos(str(contract_address)):
        if str(utxo.input.transaction_id) == tx_id:
            return utxo
    raise Exception(f"UTxO not found for transaction {tx_id}")


@dataclass
class HelloWorldRedeemer(PlutusData):
    CONSTR_ID = 0
    msg: bytes


context = BlockFrostChainContext(
    project_id=env("BLOCKFROST_API_KEY"),
    base_url="https://cardano-preview.blockfrost.io/api/",
)

signing_key = PaymentSigningKey.load("me.sk")

validator = read_validator()

# get utxo to spend
utxo = get_utxo_from_str(context, sys.argv[1], Address(
    payment_part=validator["script_hash"],
    network=Network.TESTNET,
))

# build redeemer
redeemer = Redeemer(data=HelloWorldRedeemer(msg=b"Hello, World!"))

# execute transaction
tx_hash = unlock(
    utxo=utxo,
    from_script=validator["script_bytes"],
    redeemer=redeemer,
    signing_key=signing_key,
    owner=PaymentVerificationKey.from_signing_key(signing_key).hash(),
    context=context,
)

unlocked_amount = utxo.output.amount.coin

# Record the transaction hash, redeemer, amount, and timestamp for reference
import csv
from datetime import datetime

if not os.path.exists('unlock_records'):
    os.makedirs('unlock_records')
    
# Check if file exists to determine if we need to write headers
file_exists = os.path.isfile('unlock_records/unlock_records.csv')

with open('unlock_records/unlock_records.csv', 'a', newline='') as f:
    fieldnames = ['timestamp', 'tx_hash', 'unlocked_amount (tADA)', 'redeemer', 'status', 'message']
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    
    if not file_exists:
        writer.writeheader()
        
    writer.writerow({
        'timestamp': datetime.now().isoformat(),
        'tx_hash': tx_hash,
        'unlocked_amount (tADA)': unlocked_amount/1_000_000,  # convert to tADA
        'redeemer': redeemer.to_cbor_hex(),
        'status': 'success',
        'message': 'Trip completed and payment of {} tADA made'.format(unlocked_amount/1_000_000)
    })

print(
    f"{unlocked_amount} lovelace unlocked from the contract\n\tTx ID: {tx_hash}\n\tRedeemer: {redeemer.to_cbor_hex()}"
)

# Example usage: python ryde_escrow_unlock.py <tx_hash>
# where <tx_hash> is the transaction hash output from ryde_escrow_lock.py
# The script will unlock the funds locked in that transaction
# and record the unlock transaction hash and redeemer in unlock_records/unlock_record.txt

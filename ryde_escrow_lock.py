from dataclasses import dataclass
from pycardano import (
    Address,
    BlockFrostChainContext,
    Network,
    PaymentSigningKey,
    PaymentVerificationKey,
    PlutusData,
    PlutusV3Script,
    ScriptHash,
    TransactionBuilder,
    TransactionOutput,
)
from pycardano.hash import (
    VerificationKeyHash,
    TransactionId,
    ScriptHash,
)
import json
import os
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


def lock(
        amount: int,
        into: ScriptHash,
        datum: PlutusData,
        signing_key: PaymentSigningKey,
        context: BlockFrostChainContext,
) -> TransactionId:
    # read addresses
    with open("me.addr", "r") as f:
        input_address = Address.from_primitive(f.read())
    contract_address = Address(
        payment_part=into,
        network=Network.TESTNET,
    )

    # build transaction
    builder = TransactionBuilder(context=context)
    builder.add_input_address(input_address)
    builder.add_output(
        TransactionOutput(
            address=contract_address,
            amount=amount,
            datum=datum,
        )
    )
    signed_tx = builder.build_and_sign(
        signing_keys=[signing_key],
        change_address=input_address,
    )

    # submit transaction
    context.submit_tx(signed_tx)
    return signed_tx.id


@dataclass
class HelloWorldDatum(PlutusData):
    CONSTR_ID = 0
    owner: bytes


context = BlockFrostChainContext(
    project_id=env("BLOCKFROST_API_KEY"),
    base_url="https://cardano-preview.blockfrost.io/api/",
)

signing_key = PaymentSigningKey.load("me.sk")

validator = read_validator()

owner = PaymentVerificationKey.from_signing_key(signing_key).hash()

datum = HelloWorldDatum(owner=owner.to_primitive())

amount = 2_000_000

tx_hash = lock(
    amount=amount,
    into=validator["script_hash"],
    datum=datum,
    signing_key=signing_key,
    context=context,
)

# Write the transaction hash and datum to a csv in output file for later use [amount, tx_hash, datum, message, success/failure]
if not os.path.exists("output"):
    os.makedirs("output")
with open("output/locked.csv", "a", newline="") as csvfile:
    writer = csv.writer(csvfile)
    # make the amount dynamic based on the amount locked
    # add headers
    if os.stat("output/locked.csv").st_size == 0:
        writer.writerow(["amount", "tx_hash", "datum", "message", "status"])
    writer.writerow([
        amount // 1_000_000,
        str(tx_hash),
        datum.to_cbor_hex(),
        f"Trip booked successfully for {amount // 1_000_000} tADA",
        "success"
    ])

print(
    f"tADA locked into the contract\n\tTx ID: {tx_hash}\n\tDatum: {datum.to_cbor_hex()}\n\tAmount: {amount // 1_000_000} tADA"
)
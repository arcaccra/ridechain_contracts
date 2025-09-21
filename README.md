# Cardano Contracts Helper

This script (`contract.py`) loads local keys and a Plutus script, initializes a Blockfrost chain context, and prints out helpful metadata like buyer/seller addresses and the script address.

## Prerequisites
- Python 3.8+
- Blockfrost Project ID for Preprod (TESTNET)
- Key and script files present under `trip/` directory:
  - `trip/buyer.skey`
  - `trip/buyer.vkey`
  - `trip/seller.addr` (bech32 string or JSON with `{ "address": "..." }`)
  - `trip/script.plutus` (raw CBOR-hex string or JSON with `cborHex` and optional version hints)

## Install
```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configure
Export your Blockfrost Project ID (optional if you keep the default in code):
```
export BLOCKFROST_PROJECT_ID=preprodXXXXXXXXXXXX
```

## Run
```
python contract.py
```
You should see output similar to:
```
Network: Network.TESTNET
Buyer Address: addr_test1...
Seller Address: addr_test1...
Script Hash: ScriptHash(...)
Script Address: addr_test1...
```

## Notes
- The script does not submit transactions; it only loads artifacts and prints derived information.
- `script.plutus` JSON is expected to include a `cborHex` field. If it contains `type`, `typeName` or `plutusVersion` containing `v2`, the script is treated as Plutus V2; otherwise Plutus V1.

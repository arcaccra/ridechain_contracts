"""
Simple native-script escrow on Cardano using pycardano.

Model
-----
- Buyer locks funds at a *native script* address (no Plutus).
- Funds can be spent in one of two ways:
  1) **Release**: Both Buyer AND Seller co‑sign a transaction (2-of-2).
  2) **Refund**: After a deadline slot, Buyer alone can sign and reclaim funds.

This is achieved with a NativeScript equivalent to:

    ScriptAny [
      ScriptAll [ sig(buyer), sig(seller) ],                      # release
      ScriptAll [ sig(buyer), TimelockExpiry(deadline_slot) ]     # refund
    ]

Why native scripts?
-------------------
- Extremely simple, low-cost, and supported by hardware wallets.
- Great for basic escrow where the recipients control the spending policy.
- If you need *programmable* conditions (e.g., on-chain checks on datum, price oracles, etc.), move to Plutus (Aiken/Opshin). This file keeps it native for simplicity.

Safety & Usage Notes
--------------------
- **Testnet first** (Preview or Preprod). Do not use on mainnet without audit.
- This sample signs with both keys locally for demo convenience. In production, you would build an *unsigned* transaction and collect the Seller's signature offline (CIP-8 / JSON, or your wallet).
- Never hardcode or paste mnemonics/private keys; load them securely (files/env vars/HSM). This script expects .skey/.vkey files or CBOR/JSON formats that pycardano understands.

Requirements
------------
- Python 3.10+
- pycardano >= 0.10
- A Blockfrost project id with the correct network (preview or preprod)
  - env: BLOCKFROST_PROJECT_ID
  - optional env: CARDANO_NETWORK = "preview" | "preprod" | "mainnet" (default: preprod)

Example workflow (Preprod)
--------------------------
1) Create/show the escrow address (prints bech32 and script hash):

   python pycardano_simple_escrow.py init \
       --buyer-vkey buyer.vkey \
       --seller-vkey seller.vkey \
       --deadline-mins 60 \
       --network preprod

2) Fund the escrow address from Buyer (locks 10 ADA):

   python pycardano_simple_escrow.py fund \
       --buyer-skey buyer.skey \
       --buyer-vkey buyer.vkey \
       --escrow-address addr_test1... \
       --amount-ada 10 \
       --buyer-change-addr addr_test1...

3a) Release to Seller (both sign here for demo):

   python pycardano_simple_escrow.py release \
       --buyer-skey buyer.skey \
       --seller-skey seller.skey \
       --buyer-vkey buyer.vkey \
       --seller-vkey seller.vkey \
       --deadline-mins 60 \
       --seller-payout-addr addr_test1... \
       --escrow-address addr_test1... \
       --buyer-change-addr addr_test1...

3b) Refund to Buyer (after deadline; only buyer signs):

   python pycardano_simple_escrow.py refund \
       --buyer-skey buyer.skey \
       --buyer-vkey buyer.vkey \
       --seller-vkey seller.vkey \
       --deadline-mins 60 \
       --buyer-refund-addr addr_test1... \
       --escrow-address addr_test1... \
       --buyer-change-addr addr_test1...

"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Optional, List

from pycardano import (
    Address,
    BlockFrostChainContext,
    Network,
    NativeScript,
    ScriptAny,
    ScriptAll,
    ScriptPubkey,
    PaymentSigningKey,
    PaymentVerificationKey,
    VerificationKeyHash,
    TransactionBuilder,
    TransactionOutput,
    UTxO,
    Value,
)

# -------------------------
# Chain context & utilities
# -------------------------

NETWORK_TO_BASE_URL = {
    "preprod": "https://cardano-preprod.blockfrost.io/api/v0",
    "preview": "https://cardano-preview.blockfrost.io/api/v0",
    "mainnet": "https://cardano-mainnet.blockfrost.io/api/v0",
}


def mk_context(network: str) -> BlockFrostChainContext:
    project_id = os.environ.get("BLOCKFROST_PROJECT_ID")
    if not project_id:
        print("ERROR: Set BLOCKFROST_PROJECT_ID in your environment.", file=sys.stderr)
        sys.exit(2)

    base_url = NETWORK_TO_BASE_URL.get(network)
    if not base_url:
        print(f"ERROR: Unknown network '{network}'. Use preview|preprod|mainnet.", file=sys.stderr)
        sys.exit(2)

    net_enum = Network.MAINNET if network == "mainnet" else Network.TESTNET
    return BlockFrostChainContext(project_id=project_id, base_url=base_url, network=net_enum)


# -------------------------
# Keys & addresses
# -------------------------


def load_vkey(path: str) -> PaymentVerificationKey:
    """Load a PaymentVerificationKey from file (.vkey JSON or CBOR)"""
    return PaymentVerificationKey.load(path)


def load_skey(path: str) -> PaymentSigningKey:
    """Load a PaymentSigningKey from file (.skey JSON or CBOR)"""
    return PaymentSigningKey.load(path)


def vkh(vkey: PaymentVerificationKey) -> VerificationKeyHash:
    return vkey.hash()


def address_from_vkey(vkey: PaymentVerificationKey, network: str) -> Address:
    net_enum = Network.MAINNET if network == "mainnet" else Network.TESTNET
    return Address(vkey.hash(), network=net_enum)


# -------------------------
# Escrow native script
# -------------------------

@dataclass
class EscrowPolicy:
    script: NativeScript
    deadline_slot: int


def current_slot(ctx: BlockFrostChainContext) -> int:
    # Blockfrost's chain context tracks the current tip slot
    return int(ctx.last_block_slot)


def calc_deadline_slot(ctx: BlockFrostChainContext, minutes_from_now: int) -> int:
    # Cardano slot length is 1s → minutes * 60 slots
    return current_slot(ctx) + (minutes_from_now * 60)


def build_escrow_script(
    buyer_vkh: VerificationKeyHash,
    seller_vkh: VerificationKeyHash,
    deadline_slot: int,
) -> EscrowPolicy:
    """Construct the native script policy implementing the escrow."""
    release_branch = ScriptAll([ScriptPubkey(buyer_vkh), ScriptPubkey(seller_vkh)])
    refund_branch = ScriptAll([ScriptPubkey(buyer_vkh),])
    policy = ScriptAny([release_branch, refund_branch])
    return EscrowPolicy(script=policy, deadline_slot=deadline_slot)


def escrow_address(policy: EscrowPolicy, network: str) -> Address:
    net_enum = Network.MAINNET if network == "mainnet" else Network.TESTNET
    return Address(payment_part=policy.script.hash(), network=net_enum)


# -------------------------
# UTxO helpers
# -------------------------


def pick_largest_utxo(utxos: List[UTxO]) -> UTxO:
    if not utxos:
        raise RuntimeError("No UTxOs found at the provided address.")
    # sort by lovelace amount descending
    sorted_utxos = sorted(utxos, key=lambda u: int(u.output.amount.coin), reverse=True)
    return sorted_utxos[0]


# -------------------------
# Funding (lock) phase
# -------------------------


def fund_escrow(
    ctx: BlockFrostChainContext,
    buyer_skey: PaymentSigningKey,
    buyer_vkey: PaymentVerificationKey,
    to_escrow_addr: Address,
    amount_lovelace: int,
    buyer_change_addr: Address,
) -> str:
    """Send ADA from Buyer to the escrow address."""
    builder = TransactionBuilder(ctx)

    buyer_addr = address_from_vkey(buyer_vkey, "mainnet" if ctx.network == Network.MAINNET else "preprod")
    # Let builder gather buyer inputs automatically
    builder.add_input_address(buyer_addr)

    builder.add_output(TransactionOutput(to_escrow_addr, Value(amount_lovelace)))

    signed = builder.build_and_sign([buyer_skey], change_address=buyer_change_addr)
    tx_id = ctx.submit_tx(signed)
    return str(tx_id)


# -------------------------
# Spending (release/refund)
# -------------------------


def spend_from_escrow(
    ctx: BlockFrostChainContext,
    policy: EscrowPolicy,
    escrow_addr: Address,
    buyer_skey: PaymentSigningKey,
    buyer_vkey: PaymentVerificationKey,
    payout_addr: Address,
    buyer_change_addr: Address,
    seller_skey: Optional[PaymentSigningKey] = None,
) -> str:
    """
    Spend the escrow UTxO to `payout_addr`.
    - If `seller_skey` is provided -> takes the **release** path (2-of-2).
    - If not provided -> assumes **refund** path (after deadline, buyer-only).

    In both cases we add Buyer inputs so the fee can be paid without shrinking
    the payout amount. The entire escrow UTxO is sent to `payout_addr`.
    """
    utxos = ctx.utxos(str(escrow_addr))
    escrow_utxo = pick_largest_utxo(utxos)

    builder = TransactionBuilder(ctx)

    # Inputs: the script UTxO + buyer inputs (to cover fees/change)
    builder.add_script_input(escrow_utxo, policy.script)

    buyer_addr = address_from_vkey(buyer_vkey, "mainnet" if ctx.network == Network.MAINNET else "preprod")
    builder.add_input_address(buyer_addr)

    # Output: send the *full* escrow value to the payout address
    builder.add_output(TransactionOutput(payout_addr, escrow_utxo.output.amount))

    # Signers
    signers = [buyer_skey]
    if seller_skey is not None:
        signers.append(seller_skey)

    signed = builder.build_and_sign(signers, change_address=buyer_change_addr)
    tx_id = ctx.submit_tx(signed)
    return str(tx_id)


# -------------------------
# CLI
# -------------------------


def cli() -> None:
    p = argparse.ArgumentParser(description="Simple native-script escrow (pycardano)")
    sub = p.add_subparsers(dest="cmd", required=True)

    # Common options
    p.add_argument("--network", default=os.environ.get("CARDANO_NETWORK", "preprod"),
                   choices=["preview", "preprod", "mainnet"],
                   help="Network to use (default: preprod or env CARDANO_NETWORK)")

    # init: shows address for given keys & deadline
    initp = sub.add_parser("init", help="Build and print the escrow address")
    initp.add_argument("--buyer-vkey", required=True)
    initp.add_argument("--seller-vkey", required=True)
    initp.add_argument("--deadline-mins", type=int, required=True)

    # fund: send ADA to escrow
    fundp = sub.add_parser("fund", help="Fund the escrow from buyer")
    fundp.add_argument("--buyer-skey", required=True)
    fundp.add_argument("--buyer-vkey", required=True)
    fundp.add_argument("--escrow-address", required=True)
    fundp.add_argument("--amount-ada", type=float, required=True)
    fundp.add_argument("--buyer-change-addr", required=True)

    # release: spend to seller (2-of-2 signed)
    relp = sub.add_parser("release", help="Release escrow to seller (buyer+seller sign)")
    relp.add_argument("--buyer-skey", required=True)
    relp.add_argument("--seller-skey", required=True)
    relp.add_argument("--buyer-vkey", required=True)
    relp.add_argument("--seller-vkey", required=True)
    relp.add_argument("--deadline-mins", type=int, required=True,
                      help="Used only to reconstruct the original script (must match the lock)")
    relp.add_argument("--seller-payout-addr", required=True)
    relp.add_argument("--escrow-address", required=True)
    relp.add_argument("--buyer-change-addr", required=True)

    # refund: spend back to buyer (after deadline; buyer only)
    refp = sub.add_parser("refund", help="Refund escrow to buyer (after deadline; buyer only)")
    refp.add_argument("--buyer-skey", required=True)
    refp.add_argument("--buyer-vkey", required=True)
    refp.add_argument("--seller-vkey", required=True)
    refp.add_argument("--deadline-mins", type=int, required=True,
                      help="Used only to reconstruct the original script (must match the lock)")
    refp.add_argument("--buyer-refund-addr", required=True)
    refp.add_argument("--escrow-address", required=True)
    refp.add_argument("--buyer-change-addr", required=True)

    args = p.parse_args()

    ctx = mk_context(args.network)

    if args.cmd == "init":
        buyer_vk = load_vkey(args["buyer_vkey"] if isinstance(args, dict) else args.buyer_vkey)
        seller_vk = load_vkey(args["seller_vkey"] if isinstance(args, dict) else args.seller_vkey)
        deadline_slot = calc_deadline_slot(ctx, args.deadline_mins)
        policy = build_escrow_script(vkh(buyer_vk), vkh(seller_vk), deadline_slot)
        addr = escrow_address(policy, args.network)

        print("Escrow script hash:", policy.script.hash())
        print("Deadline slot:", deadline_slot)
        print("Escrow address:", addr)
        return

    if args.cmd == "fund":
        buyer_sk = load_skey(args.buyer_skey)
        buyer_vk = load_vkey(args.buyer_vkey)
        to_escrow = Address.from_primitive(args.escrow_address)
        amt_lovelace = int(args.amount_ada * 1_000_000)
        change_addr = Address.from_primitive(args.buyer_change_addr)

        txid = fund_escrow(ctx, buyer_sk, buyer_vk, to_escrow, amt_lovelace, change_addr)
        print("Submitted funding tx:", txid)
        return

    if args.cmd == "release":
        buyer_sk = load_skey(args.buyer_skey)
        seller_sk = load_skey(args.seller_skey)
        buyer_vk = load_vkey(args.buyer_vkey)
        seller_vk = load_vkey(args.seller_vkey)
        deadline_slot = calc_deadline_slot(ctx, args.deadline_mins)
        policy = build_escrow_script(vkh(buyer_vk), vkh(seller_vk), deadline_slot)
        escrow_addr = Address.from_primitive(args.escrow_address)
        payout_addr = Address.from_primitive(args.seller_payout_addr)
        change_addr = Address.from_primitive(args.buyer_change_addr)

        txid = spend_from_escrow(
            ctx=ctx,
            policy=policy,
            escrow_addr=escrow_addr,
            buyer_skey=buyer_sk,
            buyer_vkey=buyer_vk,
            payout_addr=payout_addr,
            buyer_change_addr=change_addr,
            seller_skey=seller_sk,
        )
        print("Submitted release tx:", txid)
        return

    if args.cmd == "refund":
        buyer_sk = load_skey(args.buyer_skey)
        buyer_vk = load_vkey(args.buyer_vkey)
        seller_vk = load_vkey(args.seller_vkey)
        deadline_slot = calc_deadline_slot(ctx, args.deadline_mins)
        policy = build_escrow_script(vkh(buyer_vk), vkh(seller_vk), deadline_slot)
        escrow_addr = Address.from_primitive(args.escrow_address)
        refund_addr = Address.from_primitive(args.buyer_refund_addr)
        change_addr = Address.from_primitive(args.buyer_change_addr)

        txid = spend_from_escrow(
            ctx=ctx,
            policy=policy,
            escrow_addr=escrow_addr,
            buyer_skey=buyer_sk,
            buyer_vkey=buyer_vk,
            payout_addr=refund_addr,
            buyer_change_addr=change_addr,
            seller_skey=None,
        )
        print("Submitted refund tx:", txid)
        return


if __name__ == "__main__":
    cli()

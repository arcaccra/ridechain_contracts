use aiken/collection/list
use cardano/assets as assets
use cardano/address
use cardano/transaction.{Output, OutputReference, Transaction}
use aiken/crypto.{VerificationKeyHash}
use aiken/builtin

pub type EscrowDatum {
  rider: VerificationKeyHash,
  driver: VerificationKeyHash,
  fare_lovelace: Int,
  secret_hash: ByteArray,     // blake2b_256(secret)
  deadline: Int,              // POSIX ms
}

pub type EscrowRedeemer {
  ClaimWithSecret { secret: ByteArray },
  DualSignClaim,
  Refund,
}

fn paid_to(hash: VerificationKeyHash, tx: Transaction) -> Int {
  let addr = address.from_verification_key(hash)
  let outs = list.filter(tx.outputs, fn (o: Output) { o.address == addr })
  let total = list.foldl(outs, assets.zero, fn (o, acc) { assets.merge(o.value, acc) })
  assets.lovelace_of(total)
}

validator escrow {
  spend(datum_opt: Option<EscrowDatum>, r: EscrowRedeemer, _self_ref: OutputReference, tx: Transaction) {
    expect Some(d) = datum_opt

    when r is {
      ClaimWithSecret { secret } ->
        builtin.blake2b_256(secret) == d.secret_hash
        && paid_to(d.driver, tx) >= d.fare_lovelace

      DualSignClaim ->
        -- require both signatures; use extra_signatories (VK hashes)
        list.member(tx.extra_signatories, d.rider)
        && list.member(tx.extra_signatories, d.driver)
        && paid_to(d.driver, tx) >= d.fare_lovelace

      Refund ->
        -- after deadline and signed by rider
        tx.validity_range.lower >= d.deadline
        && list.member(tx.extra_signatories, d.rider)
    }
  }
  else(_) { fail }
}
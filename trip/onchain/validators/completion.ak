use aiken/crypto.{VerificationKeyHash}
use aiken/builtin
use cardano/transaction.{OutputReference, Transaction}

pub type CompletionDatum {
  rider: VerificationKeyHash,
  driver: VerificationKeyHash,
  trip_id: ByteArray,
  secret_hash: ByteArray,
}

pub type CompletionRedeemer {
  BothSigned,
  WithSecret { secret: ByteArray },
}

validator completion {
  spend(datum_opt: Option<CompletionDatum>, r: CompletionRedeemer, _self_ref: OutputReference, tx: Transaction) {
    expect Some(d) = datum_opt
    when r is {
      BothSigned ->
        list.member(tx.extra_signatories, d.rider)
        && list.member(tx.extra_signatories, d.driver)
      WithSecret { secret } ->
        builtin.blake2b_256(secret) == d.secret_hash
    }
  }
  else(_) { fail }
}
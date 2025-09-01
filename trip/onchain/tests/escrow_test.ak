use aiken/test
use validators/escrow

test "escrow pays driver on correct secret" {
  // Build a dummy context with datum + redeemer
  // (Aiken’s test helpers construct ScriptContext/Tx; abbreviated here)
  let rider = #"a1"
  let driver = #"b2"
  let fare = 5_000_000
  let secret = #"deadbeef"
  let datum = EscrowDatum { rider, driver, fare_lovelace: fare, secret_hash: blake2b_256(secret), deadline: time.from_posix(0) + 3600 }
  let redeemer = EscrowRedeemer::ClaimWithSecret { secret }

  // ctx pays >= fare to driver
  let ctx = test.tx()
    |> test.with_paid_to_pubkey_hash(driver, fare)
    |> test.to_script_context()

  test.assert_true(escrow::escrow(datum, redeemer, ctx))
}

test "escrow refunds only after deadline with rider sig" {
  let rider = #"a1"
  let driver = #"b2"
  let fare = 5_000_000
  let datum = EscrowDatum { rider, driver, fare_lovelace: fare, secret_hash: blake2b_256(#"00"), deadline: test.now() + 1000 }

  // Before deadline -> should fail
  let ctxEarly = test.tx()
    |> test.with_signer(rider)
    |> test.with_time_range(test.now(), test.now()+500)
    |> test.to_script_context()

  test.assert_false(escrow::escrow(datum, EscrowRedeemer::Refund, ctxEarly))

  // After deadline + rider signed -> ok
  let ctxLate = test.tx()
    |> test.with_signer(rider)
    |> test.with_time_range(datum.deadline, datum.deadline + 1000)
    |> test.to_script_context()

  test.assert_true(escrow::escrow(datum, EscrowRedeemer::Refund, ctxLate))
}
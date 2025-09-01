// Booking state-machine-lite validator
// Status: Offered -> Accepted -> (Cancelled|Expired)

use aiken/builtin
use aiken/transaction.{ScriptContext, Tx}
use aiken/time
use aiken/list
use aiken/dict

pub type Status {
  Offered
  Accepted
  Cancelled
  Expired
}

pub type BookingDatum {
  rider: ByteArray        // PaymentPubKeyHash
  driver: Option<ByteArray> // None until accepted
  fare_lovelace: Int
  deposit_lovelace: Int
  expires_at: Time
  secret_hash: ByteArray  // blake2b_256(secret)
  status: Status
}

pub type BookingRedeemer {
  Accept { driver: ByteArray }
  CancelByRider
  Expire
}

fn signed_by(pkh: ByteArray, ctx: ScriptContext) -> Bool {
  Tx.signed_by(ctx.tx, pkh)
}

validator booking(d: BookingDatum, r: BookingRedeemer, ctx: ScriptContext) -> Bool {
  // Enforce single consumption (no minting/policy logic here)
  // Validate transitions:
  when r is {
    Accept { driver } ->
      // Only from Offered -> Accepted
      d.status == Offered
      && signed_by(driver, ctx)
      && {
        // New datum on continuing output must set driver and status=Accepted, keep same secret_hash and fare
        let outs = Tx.script_outputs_at(ctx.tx, ctx.script_hash);
        // exactly one continuing output expected
        list.length(outs) == 1
        && {
          let {datum: new_datum, ..} = list.head(outs);
          when new_datum is {
            Some(Data::map m) ->
              // decode expected fields (shallow check to keep script small)
              // for simplicity, require the driver bytes to equal `driver` and status tag changed
              // (In a real app, decode to BookingDatum fully or carry a state-NFT)
              builtin.trace_if_false("driver set",
                dict.get(m, Data::bytestring("driver")) == Some(Data::bytestring(driver))) &&
              builtin.trace_if_false("status accepted",
                dict.get(m, Data::bytestring("status")) == Some(Data::bytestring("Accepted")))
            _ -> builtin.error("missing datum")
          }
        }
      }

    CancelByRider ->
      // Rider can cancel if still Offered and before expiry
      d.status == Offered
      && signed_by(d.rider, ctx)
      && Tx.valid_range(ctx.tx).upper < d.expires_at

    Expire ->
      // Anyone can expire after expiry, moving to Expired (refund happens off-chain selection)
      d.status == Offered
      && Tx.valid_range(ctx.tx).lower >= d.expires_at
  }
}
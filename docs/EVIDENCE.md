# Capture evidence (read-only)

Observed from IRCTC public chart JSON on 2026-10-14. These are observations, not a guarantee of a stable public API.

## Verified operations

| Operation | Method / path | Request fields | Response fields used |
| --- | --- | --- | --- |
| Train composition | `POST /online-charts/api/trainComposition` | `trainNo`, `jDate`, `boardingStation` | `cdd[]` (`coachName`, `classCode`, `positionFromEngine`, `vacantBerths`), `trainNo`, `trainName`, `from`, `to`, `trainStartDate`, `remote`, `chartStatusResponseDto`, `error` |
| Coach composition | `POST /online-charts/api/coachComposition` | `trainNo`, `boardingStation`, `remoteStation`, `trainSourceStation`, `jDate`, `coach`, `cls` | `bdd[]` berths; coach-level `bsd[]` was empty in captures |
| Train schedule (km) | `GET /eticketing/protected/mapps1/trnscheduleenquiry/{trainNo}` | path train number | `stationList[]` with `stationCode`, `stationName`, `distance`, `stnSerialNumber` |

Live captures: train `18609` RNC–LTT on `2026-10-14`. Coach samples: `H1/1A`, `S3/SL`.

## Field meanings (from values, not names)

- **`occupancy`**: boolean on each berth nested `bsd[]` item. Captured values were only `true` and `false`. `false` appears on earlier vacant splits (e.g. RNC→BKSC); `true` appears on later occupied splits. **Eligible vacant = `occupancy is false`.** Missing occupancy is unknown, never available.
- **`enable`**: `true` on every captured berth. Not used as vacancy.
- **`vacantBerths`**: `0` on every captured coach while nested `occupancy: false` segments existed. **Not treated as individual-berth status.**
- **`distance`**: string kilometres from train origin on `stationList`. Segment km = destination distance − boarding distance. Never invent km.

## Unverified / unused

- Booking, payment, captcha, OTP, availability-enquiry write paths.
- Coach-level `bsd[]` (empty in samples; berth nested `bsd[]` is used).
- `quotaCntStn`, `avlRemoteForBooking`, `destinationStation` on train composition (null in sample).

## Fixture vs live

Default `DATA_SOURCE=auto` serves captured JSON under `fixtures/` when present, then live charts through hidden Chrome CDP (`window.fetch` inside an `irctc.co.in` tab on Xvfb; no visible window). Direct Python HTTP from this host times out. Fixture output is labelled fixture-based. Live CDP still only calls the three read paths above.

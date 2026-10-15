# IRCTC Chart Vacant

Read-only analyser for IRCTC **online chart** composition. It finds the longest
continuous vacant berth run on a requested journey and ranks by verified
kilometres, then consecutive segments.

It never books, reserves, pays, or submits a reservation.

## What it does

1. Validates train number, stations, date, and classes.
2. Loads train composition (`cdd[]`) and discovers coaches/classes actually present.
3. Loads coach composition (`bdd[]` / nested `bsd[]`) for selected classes.
4. Maps boarding→destination onto a verified schedule (`stationList[].distance`).
5. Treats `occupancy: false` as vacant, `true` as occupied, anything else as unknown.
6. Merges only **adjacent** vacant splits. Gaps stay gaps.
7. Ranks: verified km, then segment count, then coverage, then coach/berth.

## Requirements

- Python 3.11+
- Google Chrome or Chromium (live chart reads)
- Xvfb (`xvfb` / `xvfb-run`) so Chrome stays off the desktop

## Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
./scripts/start-charts-chrome.sh
DATA_SOURCE=auto uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765

Default enquiry in the UI uses captured train **18609** RNC→GAYA on 2026-10-14, class 1A (fixture `H1`).

## Configuration

See `.env.example`. Copy it to `.env` locally; never commit `.env` or cookie files.

| Variable | Meaning |
| --- | --- |
| `DATA_SOURCE` | `auto` (saved fixture, then Chrome CDP live charts), `fixture`, `synthetic`, `live` (CDP), or `http` (direct Python HTTP) |
| `CHROME_CDP` | Chrome DevTools endpoint (default `http://127.0.0.1:9222`) |
| `CHARTS_XVFB_DISPLAY` | Hidden display for charts Chrome (default `:99`) |
| `IRCTC_COOKIE_FILE` / `IRCTC_COOKIES` | Optional session for `DATA_SOURCE=http` only |
| `IRCTC_TIMEOUT_SECONDS` | In-page fetch / CDP timeout (default 20) |

Live reads attach to a Chrome on port 9222 and run `window.fetch()` inside an `irctc.co.in` tab. That Chrome runs on a private Xvfb display so no window is shown on the desktop. Direct Python HTTP to IRCTC is usually reset or timed out from this host.

Allowed paths only:

- `POST /online-charts/api/trainComposition`
- `POST /online-charts/api/coachComposition`
- `GET /eticketing/protected/mapps1/trnscheduleenquiry/{trainNo}`

Booking and payment paths are rejected in code. If no hidden Chrome answers on CDP, `scripts/start-charts-chrome.sh` starts Xvfb plus a background Chrome parked on `/online-charts/`. `--headless=new` is not used (IRCTC rejects that user-agent). A visible Chrome already on 9222 is replaced.

## Architecture

```
UI (static/) → POST /api/analyze → validation → charts adapter
  → train composition → schedule (km) → coach composition
  → route/segment engine → vacancy (occupancy) → ranking → table + layout
```

Vacancy interpretation lives in `app/vacancy.py` so a corrected field meaning does not rewrite ranking.

## Security

- Read-only. Booking, payment, captcha, and OTP paths are hard-blocked.
- Secrets in logs are redacted (`cookie`, `authorization`, tokens).
- Do not commit `.env`, cookie files, or a signed-in Chrome profile.

See `SECURITY.md`.

## Known limitations

- Captured `vacantBerths` is not trusted for individual berths.
- If the schedule cannot be loaded, ranking falls back to consecutive segments and km is shown as unavailable.
- Fixture mode is **not** live IRCTC data.
- Only coaches with fixtures (or a successful live read) are analysed; other coaches are reported as failed fetches.
- Station order and km come from `trnscheduleenquiry`, which is a session-gated IRCTC read in live mode.

Evidence: `docs/EVIDENCE.md`.

## License

MIT. See `LICENSE`.

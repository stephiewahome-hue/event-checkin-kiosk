# Event Check-in Kiosk (Async Badge Printing with Redis + Webhooks)

A small check-in kiosk for a conference. Staff scan an attendee's QR code, a badge is printed,
and the screen shows **Checked In** only once the printer has actually confirmed.

> **Credit:** the scenario (Solstice Events Co. and its badge-printer pivot) comes from a
> pivot-simulation exercise I came across online. The design and code here are my own implementation.

This project explores a common real-world change: a printer vendor retires its synchronous
API, so the app must switch to an **asynchronous model** (message queue + webhook callback).

## Screenshots

**Kiosk screen:** badges show *Printing...* until the printer's webhook confirms, then *Checked In*.

![Kiosk](screenshots/kiosk.png)

**Duplicate scans are rejected** (both while printing and after check-in), so no second badge is printed.

![Duplicate rejected](screenshots/duplicate-rejected.png)

**Printer worker:** confirmations arrive in a different order than the scans, and sometimes twice.

![Worker terminal](screenshots/worker-terminal.png)

## The problem

- **Before:** the app called the printer API and waited for the reply. If the printer was slow, the kiosk froze.
- **After:** the app drops a print request on a queue and returns immediately. The vendor calls a
  webhook when the job finishes, and the screen shows **Printing...** until then.

## What it handles

| Concern | How |
|---|---|
| Duplicate scans (double badge) | Redis `SET ... NX`: atomic, so two simultaneous scans can't both succeed |
| Out-of-order confirmations | Each print job has a unique ID; webhooks are matched by ID, not arrival order |
| Repeated webhooks | Idempotency marker per job: only the first callback is processed |
| Forged webhooks | HMAC-SHA256 signature checked on every callback (`X-Signature` header) |
| Failed prints | Status is cleared so staff can scan again |

## Architecture

```
Browser (kiosk.html)  --POST /scan-->  Flask app  --push job-->  Redis queue
        ^                                  ^                          |
        | GET /status (polling)            |                          v
        +----------------------------  Redis (status)        worker.py (fake printer vendor)
                                           ^                          |
                                           +------ POST /webhook -----+
                                                   (signed callback)
```

Status per attendee: `not_checked_in` -> `pending` -> `checked_in`

## Tech

Python, Flask, Redis (queue + state), plain HTML/JS front end.

## Run it

1. Start Redis (on Windows I used WSL: `sudo service redis-server start`).
2. Install dependencies:
   ```
   python -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   ```
3. In three terminals:
   ```
   python app.py       # kiosk server
   python worker.py    # fake printer vendor
   python test_flow.py # scans 3 attendees + duplicates
   ```
4. Open http://localhost:5000 and click **Scan QR**.

Optional: `python test_scan.py` (scan logic) and `python test_security.py` (forged webhooks are rejected).

Set a real secret with the `WEBHOOK_SECRET` environment variable (the default is for local testing only).

## What I'd add for production

Managed queue (RabbitMQ/SQS), database for attendee records, retries and dead-letter queue for stuck
jobs, WebSockets instead of polling, camera QR scanning, HTTPS.

## What I learned

- **A queue is just a list with rules.** I used a Redis list as the message queue: the app pushes
  a job with `LPUSH` and the worker waits for work with `BRPOP`. The app never waits for the printer.
- **Atomic operations stop race conditions.** `SET ... NX` ("set only if it doesn't exist") is a single
  step in Redis, so two scans at the same instant can't both pass the duplicate check.
- **Async means expecting messy delivery.** Confirmations can arrive late, out of order, or twice.
  Giving every print job a unique ID and processing each ID only once (idempotency) made that safe.
- **Never trust an incoming webhook blindly.** Anyone who finds the URL can call it, so each callback
  is signed with HMAC-SHA256 and verified before anything changes.
- **The UI has to tell the truth.** "Checked In" is only shown after the printer confirms; until then it
  shows a pending state.
- **Bugs I hit and fixed:**
  - The worker crashed with a `TimeoutError` while idle because the connection timeout (default) was
    shorter than the 5-second blocking wait. Fix: a longer socket timeout plus a retry on timeout.
  - Redis doesn't run natively on Windows, so I set it up through WSL (Ubuntu).
  - Small setup issues (virtual environment not active, file saved with the wrong extension) taught me
    to check the basics first when the error message doesn't make sense.

# Event Check-in Kiosk (Async Badge Printing with Redis + Webhooks)

A small check-in kiosk for a conference. Staff scan an attendee's QR code, a badge is printed,
and the screen shows **Checked In** only once the printer has actually confirmed.

This project explores a common real-world change: a printer vendor retires its synchronous
API, so the app must switch to an **asynchronous model** (message queue + webhook callback).

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

(Write your own notes here: Redis lists as queues, atomic operations, idempotency, and the
timeout bug you hit and fixed.)
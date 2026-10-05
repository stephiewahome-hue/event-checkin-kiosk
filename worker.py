"""Fake badge-printer vendor.
Takes print jobs off the Redis queue, "prints" for a random time,
then calls our webhook. Because the delay is random, confirmations
arrive OUT OF ORDER, just like the real assignment says.
"""
import hashlib
import hmac
import json
import os
import random
import threading
import time

import redis
import requests

# socket_timeout must be LONGER than the brpop wait below, otherwise the
# connection gives up before Redis answers and raises TimeoutError.
r = redis.Redis(host="localhost", port=6379, decode_responses=True, socket_timeout=30)
WEBHOOK_URL = "http://localhost:5000/webhook"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "dev-secret-change-me").encode()


def send_webhook(payload):
    """Send the callback with a signature proving it came from the vendor."""
    body = json.dumps(payload).encode()
    signature = hmac.new(WEBHOOK_SECRET, body, hashlib.sha256).hexdigest()
    requests.post(
        WEBHOOK_URL,
        data=body,
        headers={"Content-Type": "application/json", "X-Signature": signature},
    )


def print_badge(job):
    delay = random.uniform(2, 8)
    print(f"[printer] printing badge for {job['name']} (job {job['job_id'][:8]}) ~{delay:.1f}s")
    time.sleep(delay)

    payload = {"job_id": job["job_id"], "result": "success"}
    send_webhook(payload)
    print(f"[printer] DONE {job['name']} -> webhook sent")

    # Sometimes the vendor sends the same callback twice (to test idempotency)
    if random.random() < 0.3:
        send_webhook(payload)
        print(f"[printer] (sent duplicate webhook for {job['name']})")


print("[printer] waiting for print jobs...")
while True:
    try:
        item = r.brpop("print_queue", timeout=5)  # blocks until a job arrives
    except redis.exceptions.TimeoutError:
        continue  # nothing arrived, just try again
    if item is None:
        continue
    job = json.loads(item[1])
    # One thread per job so jobs finish in random order
    threading.Thread(target=print_badge, args=(job,), daemon=True).start()
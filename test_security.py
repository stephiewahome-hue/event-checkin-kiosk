import hashlib
import hmac
import json
import os

import requests

BASE = "http://localhost:5000"
SECRET = os.environ.get("WEBHOOK_SECRET", "dev-secret-change-me").encode()

payload = {"job_id": "some-fake-job-id", "result": "success"}
body = json.dumps(payload).encode()
headers = {"Content-Type": "application/json"}

# 1. Attacker sends a webhook with NO signature
res = requests.post(f"{BASE}/webhook", data=body, headers=headers)
print("No signature      ->", res.status_code, res.json(), "(expected 401)")

# 2. Attacker guesses a signature
bad = {**headers, "X-Signature": "0" * 64}
res = requests.post(f"{BASE}/webhook", data=body, headers=bad)
print("Wrong signature   ->", res.status_code, res.json(), "(expected 401)")

# 3. The real vendor signs with the shared secret
good_sig = hmac.new(SECRET, body, hashlib.sha256).hexdigest()
good = {**headers, "X-Signature": good_sig}
res = requests.post(f"{BASE}/webhook", data=body, headers=good)
print("Correct signature ->", res.status_code, res.json(),
      "(expected 404: signature accepted, but that job doesn't exist)")
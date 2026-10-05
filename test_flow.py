import time

import requests

BASE = "http://localhost:5000"
IDS = ["A001", "A002", "A003"]

requests.post(f"{BASE}/reset")

for i in IDS:
    print(i, requests.post(f"{BASE}/scan", json={"attendee_id": i}).status_code)

# Duplicate scan while still pending: must be rejected
print("A001 again:", requests.post(f"{BASE}/scan", json={"attendee_id": "A001"}).json())

# Watch the statuses change (up to ~20 seconds)
for _ in range(20):
    statuses = {i: requests.get(f"{BASE}/status/{i}").json()["status"] for i in IDS}
    print(statuses)
    if all(s == "checked_in" for s in statuses.values()):
        break
    time.sleep(1)

# Duplicate scan after check-in: must also be rejected
print("A001 after check-in:", requests.post(f"{BASE}/scan", json={"attendee_id": "A001"}).json())
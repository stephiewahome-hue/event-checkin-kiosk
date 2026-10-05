import requests

BASE = "http://localhost:5000"

requests.post(f"{BASE}/reset")  # start clean

tests = [
    ("A001", "first scan, should be queued (202)"),
    ("A002", "first scan, should be queued (202)"),
    ("A003", "first scan, should be queued (202)"),
    ("A001", "DUPLICATE scan, should be rejected (409)"),
    ("A999", "unknown attendee, should be 404"),
]

for attendee_id, expectation in tests:
    res = requests.post(f"{BASE}/scan", json={"attendee_id": attendee_id})
    print(f"{attendee_id}: {res.status_code}  {res.json()}")
    print(f"   expected: {expectation}\n")

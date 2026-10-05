import hashlib
import hmac
import json
import os
import uuid

import redis
from flask import Flask, jsonify, request, send_file

app = Flask(__name__)

# Connect to Redis (running inside WSL, reachable from Windows via localhost)
r = redis.Redis(host="localhost", port=6379, decode_responses=True)

# Our 3 test attendees (QR code value -> name)
ATTENDEES = {
    "A001": "Alice Otieno",
    "A002": "Brian Mwangi",
    "A003": "Cynthia Wanjiku",
}

PRINT_QUEUE = "print_queue"  # the message queue (a Redis list)

# Secret shared ONLY between us and the printer vendor.
# In real life, set it as an environment variable and never put it in code.
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "dev-secret-change-me").encode()


def signature_is_valid(raw_body, received_signature):
    """Recompute the signature from the body and compare with the one received."""
    expected = hmac.new(WEBHOOK_SECRET, raw_body, hashlib.sha256).hexdigest()
    # compare_digest avoids timing attacks (a safe way to compare secrets)
    return hmac.compare_digest(expected, received_signature or "")


def status_key(attendee_id):
    return f"status:{attendee_id}"


@app.route("/")
def home():
    """Serve the kiosk screen."""
    return send_file("kiosk.html")


@app.route("/scan", methods=["POST"])
def scan():
    """Staff scans a QR code. Start a print job unless one already exists."""
    data = request.get_json(silent=True) or {}
    attendee_id = data.get("attendee_id")

    if attendee_id not in ATTENDEES:
        return jsonify({"error": "Unknown attendee"}), 404

    # THE DUPLICATE-SCAN GUARD
    # SET ... NX means "only set this if it does not exist yet".
    # Redis does this as ONE atomic step, so two scans at the same
    # instant can never both succeed.
    got_it = r.set(status_key(attendee_id), "pending", nx=True)

    if not got_it:
        current = r.get(status_key(attendee_id))
        return jsonify({
            "message": f"Duplicate scan rejected. Status is already '{current}'.",
            "status": current,
        }), 409

    # First scan: create a print job with a unique ID and put it on the queue
    job_id = str(uuid.uuid4())
    job = {"job_id": job_id, "attendee_id": attendee_id, "name": ATTENDEES[attendee_id]}
    r.set(f"job:{job_id}", attendee_id)  # remember which attendee this job belongs to
    r.lpush(PRINT_QUEUE, json.dumps(job))

    return jsonify({"message": "Print request queued", "status": "pending", "job_id": job_id}), 202


@app.route("/status/<attendee_id>", methods=["GET"])
def status(attendee_id):
    """The screen asks this to know what to display."""
    if attendee_id not in ATTENDEES:
        return jsonify({"error": "Unknown attendee"}), 404
    current = r.get(status_key(attendee_id)) or "not_checked_in"
    return jsonify({"attendee_id": attendee_id, "status": current})


@app.route("/webhook", methods=["POST"])
def webhook():
    """The printer vendor calls this when a print job finishes.
    Body: {"job_id": "...", "result": "success" or "failed"}
    Callbacks can arrive late, out of order, or twice, so we match by job_id."""
    # SECURITY: verify the vendor really sent this, before trusting anything in it
    raw_body = request.get_data()
    if not signature_is_valid(raw_body, request.headers.get("X-Signature")):
        return jsonify({"error": "Invalid signature"}), 401

    data = json.loads(raw_body or b"{}")
    job_id = data.get("job_id")
    result = data.get("result")

    attendee_id = r.get(f"job:{job_id}") if job_id else None
    if not attendee_id:
        return jsonify({"error": "Unknown job"}), 404

    # IDEMPOTENCY: only the first callback for a job_id is processed.
    # SET ... NX again: a repeated webhook finds the marker and is ignored.
    first_time = r.set(f"processed:{job_id}", "1", nx=True)
    if not first_time:
        return jsonify({"message": "Duplicate webhook ignored"}), 200

    # Only move pending -> checked_in. Anything else is left untouched.
    if r.get(status_key(attendee_id)) == "pending":
        if result == "success":
            r.set(status_key(attendee_id), "checked_in")
        else:
            # Print failed: clear the status so staff can scan again
            r.delete(status_key(attendee_id))

    return jsonify({"message": "Webhook processed", "attendee_id": attendee_id}), 200


@app.route("/reset", methods=["POST"])
def reset():
    """Testing helper: clear everything so you can re-run tests."""
    r.flushdb()
    return jsonify({"message": "Reset done"})


if __name__ == "__main__":
    app.run(port=5000, debug=True)
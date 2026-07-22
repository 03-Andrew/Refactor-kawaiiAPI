"""
Concurrency test for room-type lock.

Usage:
    python bookings/tests/test_lock_concurrency.py

Requires redis running on localhost:6379 and the dev server on localhost:8000.
"""

import json
import threading
import urllib.request

BASE = "http://localhost:8000/api"

SUBMIT_BODY = {
    "customer": {
        "first_name": "Test",
        "last_name": "Concurrent",
        "contact_number": "09123456789",
        "email": "test@example.com",
    },
    "rooms": [
        {
            "room_type": 1,
            "check_in": "2026-08-01",
            "check_out": "2026-08-03",
            "adult_count": 2,
            "children_count": 0,
            "extra_guest": 0,
            "price": 5000.00,
            "number_of_guests": 2,
        },
    ],
    "payment": {
        "amount": 5000.00,
    },
}

results = {"success": 0, "conflict": 0, "error": 0}
lock = threading.Lock()


def try_book(worker_id):
    url = f"{BASE}/bookings/online"
    body = json.loads(json.dumps(SUBMIT_BODY))
    body["customer"]["email"] = f"test{worker_id}@example.com"
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
    except urllib.error.HTTPError as e:
        status = e.code
    except Exception as e:
        status = str(e)

    with lock:
        if status == 201:
            results["success"] += 1
        elif status == 409:
            results["conflict"] += 1
        else:
            results["error"] += 1


def test_lock_and_book():
    """Single user: lock → book → verify lock released."""
    # Acquire lock
    lock_url = f"{BASE}/bookings/lock-room-type"
    lock_data = json.dumps({
        "room_type": 1,
        "check_in": "2026-08-01",
        "check_out": "2026-08-03",
    }).encode()
    req = urllib.request.Request(lock_url, data=lock_data,
                                 headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req)
    lock_result = json.loads(resp.read())
    print(f"Lock acquired: {lock_result}")
    assert lock_result["held"] is True

    # Verify locked_rooms in listing
    list_url = f"{BASE}/room-types/?check_in=2026-08-01&check_out=2026-08-03"
    resp = urllib.request.urlopen(list_url)
    rooms = json.loads(resp.read())
    target = [r for r in rooms if r["id"] == 1]
    if target:
        print(f"Room type 1: locked={target[0]['locked_rooms']}, "
              f"available={target[0]['available_rooms']}")

    # Submit booking with holder_id
    book_url = f"{BASE}/bookings/online"
    body = json.loads(json.dumps(SUBMIT_BODY))
    body["holder_id"] = lock_result["holder_id"]
    data = json.dumps(body).encode()
    req = urllib.request.Request(book_url, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req)
        print(f"Booking created: {resp.status}")
    except urllib.error.HTTPError as e:
        print(f"Booking failed: {e.code} {e.read().decode()[:200]}")

    # Release lock (should be no-op if booking consumed it)
    rel_url = f"{BASE}/bookings/release-room-type"
    rel_data = json.dumps({
        "room_type": 1,
        "check_in": "2026-08-01",
        "check_out": "2026-08-03",
        "holder_id": lock_result["holder_id"],
    }).encode()
    req = urllib.request.Request(rel_url, data=rel_data,
                                 headers={"Content-Type": "application/json"})
    resp = urllib.request.urlopen(req)
    print(f"Release result: {json.loads(resp.read())}")


def test_concurrent_submit(threads=10):
    """Fire N concurrent booking requests without locks — only N_available should succeed."""
    print(f"\n--- Concurrent submit test ({threads} threads) ---")
    workers = []
    for i in range(threads):
        t = threading.Thread(target=try_book, args=(i,))
        workers.append(t)

    for t in workers:
        t.start()
    for t in workers:
        t.join()

    print(f"Success: {results['success']}, Conflict: {results['conflict']}, "
          f"Error: {results['error']}")


if __name__ == "__main__":
    test_lock_and_book()
    # test_concurrent_submit(10)

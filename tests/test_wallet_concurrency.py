"""Concurrency integration test against a running PostgreSQL-backed API.

Run with the FastAPI server already running, for example:
    pytest -s tests/test_wallet_concurrency.py
"""

import json
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_BASE_URL = os.getenv("WALLET_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
REQUEST_COUNT = 50
DEBIT_AMOUNT = "10.0000"
INITIAL_BALANCE = "100.0000"


def _database_url() -> str:
    """Return the configured DB URL without logging or exposing credentials."""
    configured = os.getenv("DATABASE_URL")
    if configured:
        return configured

    env_file = PROJECT_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and stripped.startswith("DATABASE_URL="):
                return stripped.split("=", 1)[1].strip().strip("\"'")

    raise AssertionError("DATABASE_URL is not set and was not found in project .env")


def _request(path: str, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = Request(
        f"{API_BASE_URL}{path}",
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=60) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        response_body = error.read().decode("utf-8", errors="replace")
        try:
            parsed_body = json.loads(response_body)
        except json.JSONDecodeError:
            parsed_body = {"detail": response_body}
        return error.code, parsed_body
    except URLError as error:
        return 0, {"detail": str(error.reason)}


def test_50_concurrent_debits_are_atomic_and_ledgered_once() -> None:
    """Issue 50 synchronized real HTTP requests to one PostgreSQL wallet."""
    database_url = _database_url()
    scheme = urlsplit(database_url).scheme.lower()
    assert scheme.startswith("postgresql"), (
        "This integration test requires PostgreSQL; configured DATABASE_URL "
        "does not use a PostgreSQL scheme."
    )

    test_token = str(uuid.uuid4())
    user_id = f"phase2-concurrency-{test_token}"

    create_status, created = _request(
        "/wallets", "POST", {"user_id": user_id, "currency": "USD"}
    )
    assert create_status == 201, f"Wallet creation failed: HTTP {create_status}: {created}"
    wallet_id = created["id"]

    credit_status, credit = _request(
        f"/wallets/{wallet_id}/credit",
        "POST",
        {"amount": INITIAL_BALANCE, "description": f"Phase 2 seed {test_token}"},
    )
    assert 200 <= credit_status < 300, (
        f"Wallet funding failed: HTTP {credit_status}: {credit}"
    )

    start_barrier = threading.Barrier(REQUEST_COUNT)

    def send_debit(index: int) -> dict:
        description = f"Phase 2 concurrent debit {index} {test_token}"
        try:
            start_barrier.wait(timeout=30)
        except threading.BrokenBarrierError:
            return {"index": index, "description": description, "status": 0,
                    "body": {"detail": "Concurrency start barrier failed"}}
        status_code, body = _request(
            f"/wallets/{wallet_id}/debit",
            "POST",
            {"amount": DEBIT_AMOUNT, "description": description},
        )
        return {
            "index": index,
            "description": description,
            "status": status_code,
            "body": body,
        }

    # Exactly 50 worker threads reach the barrier before any sends its request.
    with ThreadPoolExecutor(max_workers=REQUEST_COUNT) as executor:
        results = list(executor.map(send_debit, range(REQUEST_COUNT)))

    successful = [r for r in results if 200 <= r["status"] < 300]
    failed = [r for r in results if not 200 <= r["status"] < 300]
    insufficient_funds = [
        r for r in failed
        if r["status"] == 400
        and "insufficient funds" in str(r["body"].get("detail", "")).lower()
    ]

    balance_status, balance = _request(f"/wallets/{wallet_id}/balance")
    ledger_status, ledger = _request(f"/wallets/{wallet_id}/ledger?limit=100&offset=0")
    assert balance_status == 200, f"Balance query failed: HTTP {balance_status}: {balance}"
    assert ledger_status == 200, f"Ledger query failed: HTTP {ledger_status}: {ledger}"

    entries = ledger["entries"]
    debit_entries = [entry for entry in entries if entry["operation_type"] == "DEBIT"]
    successful_entry_ids = {r["body"].get("id") for r in successful}
    debit_entry_ids = {entry["id"] for entry in debit_entries}
    failed_descriptions = {r["description"] for r in failed}
    failed_request_entries = [
        entry for entry in entries
        if entry.get("description") in failed_descriptions
    ]
    checks = {
        "exactly 50 requests completed": len(results) == REQUEST_COUNT,
        "exactly 10 requests succeeded": len(successful) == 10,
        "exactly 40 requests failed": len(failed) == 40,
        "all failures were insufficient-funds HTTP 400": len(insufficient_funds) == 40,
        "final wallet balance is zero": balance["balance"] == "0.0000",
        "exactly 10 DEBIT ledger entries exist": len(debit_entries) == 10,
        "every successful response has one ledger entry": (
            len(successful_entry_ids) == 10 and successful_entry_ids == debit_entry_ids
        ),
        "failed requests created no ledger entries": len(failed_request_entries) == 0,
        "total amount debited is 100": sum(float(e["amount"]) for e in debit_entries) == 100.0,
    }

    print("\nPhase 2 concurrency test results")
    print(f"  Wallet ID: {wallet_id}")
    print(f"  Successful requests: {len(successful)}")
    print(f"  Failed requests: {len(failed)}")
    print(f"  Insufficient-funds failures: {len(insufficient_funds)}")
    print(f"  Final balance: {balance['balance']}")
    print(f"  Total ledger entries (including initial credit): {ledger['total_entries']}")
    print(f"  DEBIT ledger entries: {len(debit_entries)}")
    print(f"  Total amount debited: {sum(float(e['amount']) for e in debit_entries):.2f}")
    for description, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}: {description}")

    assert all(checks.values()), "Phase 2 concurrency checks failed; see results above."
    print("PASS: Phase 2 concurrency scenario")

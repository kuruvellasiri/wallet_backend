import os

os.environ["DATABASE_URL"] = "sqlite:///./wallet_test.db"

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.database import SessionLocal
from app.main import app
from app.models import LedgerEntry, Wallet


def setup_function() -> None:
    with SessionLocal() as db:
        db.execute(delete(LedgerEntry))
        db.execute(delete(Wallet))
        db.commit()


def test_create_credit_debit_and_read_wallet_history() -> None:
    with TestClient(app) as client:
        created = client.post("/wallets", json={"user_id": 42})
        assert created.status_code == 201
        wallet_id = created.json()["id"]
        assert created.json()["balance"] == "0.00"

        credit = client.post(
            f"/wallets/{wallet_id}/credits",
            json={"amount": "25.50", "description": "Deposit"},
        )
        assert credit.status_code == 201
        assert credit.json()["balance_after"] == "25.50"

        debit = client.post(
            f"/wallets/{wallet_id}/debits",
            json={"amount": "4.25", "description": "Purchase"},
        )
        assert debit.status_code == 201
        assert debit.json()["balance_after"] == "21.25"

        balance = client.get(f"/wallets/{wallet_id}/balance")
        assert balance.status_code == 200
        assert balance.json()["balance"] == "21.25"

        history = client.get(f"/wallets/{wallet_id}/transactions?limit=1&offset=0")
        assert history.status_code == 200
        assert len(history.json()["items"]) == 1
        assert history.json()["items"][0]["transaction_type"] == "debit"


def test_rejects_duplicate_wallet_and_invalid_or_excessive_debit() -> None:
    with TestClient(app) as client:
        created = client.post("/wallets", json={"user_id": 77})
        wallet_id = created.json()["id"]

        duplicate = client.post("/wallets", json={"user_id": 77})
        assert duplicate.status_code == 409

        invalid_amount = client.post(
            f"/wallets/{wallet_id}/credits", json={"amount": "0"}
        )
        assert invalid_amount.status_code == 422

        excessive_debit = client.post(
            f"/wallets/{wallet_id}/debits", json={"amount": "0.01"}
        )
        assert excessive_debit.status_code == 409

        balance = client.get(f"/wallets/{wallet_id}/balance")
        assert balance.json()["balance"] == "0.00"


def test_unknown_wallet_returns_not_found() -> None:
    with TestClient(app) as client:
        response = client.get("/wallets/999999/balance")

    assert response.status_code == 404

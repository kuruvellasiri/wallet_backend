import os

os.environ['DATABASE_URL'] = 'sqlite:///./wallet_test.db'
os.environ['JWT_SECRET_KEY'] = 'test-only-secret-do-not-use-in-production'
os.environ['JWT_ALGORITHM'] = 'HS256'
os.environ['ACCESS_TOKEN_EXPIRE_MINUTES'] = '30'

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.database import SessionLocal
from app.main import app
from app.models import LedgerEntry, User, Wallet

TEST_USERNAME = 'phase1-test-user'
TEST_PASSWORD = 'phase1-test-password'


def login_headers(client: TestClient) -> tuple[dict[str, str], str]:
    registered = client.post('/auth/register', json={'username': TEST_USERNAME, 'password': TEST_PASSWORD})
    assert registered.status_code == 201
    response = client.post('/auth/login', json={'username': TEST_USERNAME, 'password': TEST_PASSWORD})
    assert response.status_code == 200
    return {'Authorization': f"Bearer {response.json()['access_token']}"}, registered.json()['id']


def setup_function() -> None:
    with SessionLocal() as db:
        db.execute(delete(LedgerEntry))
        db.execute(delete(Wallet))
        db.execute(delete(User))
        db.commit()


def test_create_credit_debit_and_read_wallet_history() -> None:
    with TestClient(app) as client:
        headers, user_id = login_headers(client)
        created = client.post('/wallets', json={'user_id': user_id}, headers=headers)
        assert created.status_code == 201
        wallet_id = created.json()['id']
        assert created.json()['balance'] == '0.0000'

        credit = client.post(f'/wallets/{wallet_id}/credit', json={'amount': '25.50', 'description': 'Deposit'}, headers=headers)
        assert credit.status_code == 200
        assert credit.json()['balance_after'] == '25.5000'

        debit = client.post(f'/wallets/{wallet_id}/debit', json={'amount': '4.25', 'description': 'Purchase'}, headers=headers)
        assert debit.status_code == 200
        assert debit.json()['balance_after'] == '21.2500'

        balance = client.get(f'/wallets/{wallet_id}/balance', headers=headers)
        assert balance.status_code == 200
        assert balance.json()['balance'] == '21.2500'

        history = client.get(f'/wallets/{wallet_id}/ledger?limit=1&offset=0', headers=headers)
        assert history.status_code == 200
        assert len(history.json()['entries']) == 1
        assert history.json()['entries'][0]['operation_type'] == 'DEBIT'


def test_rejects_duplicate_wallet_and_invalid_or_excessive_debit() -> None:
    with TestClient(app) as client:
        headers, user_id = login_headers(client)
        created = client.post('/wallets', json={'user_id': user_id}, headers=headers)
        wallet_id = created.json()['id']
        duplicate = client.post('/wallets', json={'user_id': user_id}, headers=headers)
        assert duplicate.status_code == 409
        invalid_amount = client.post(f'/wallets/{wallet_id}/credit', json={'amount': '0'}, headers=headers)
        assert invalid_amount.status_code == 422
        excessive_debit = client.post(f'/wallets/{wallet_id}/debit', json={'amount': '0.01'}, headers=headers)
        assert excessive_debit.status_code == 400
        balance = client.get(f'/wallets/{wallet_id}/balance', headers=headers)
        assert balance.json()['balance'] == '0.0000'


def test_unknown_wallet_returns_not_found() -> None:
    with TestClient(app) as client:
        headers, _ = login_headers(client)
        response = client.get('/wallets/00000000-0000-0000-0000-000000000001/balance', headers=headers)
    assert response.status_code == 404

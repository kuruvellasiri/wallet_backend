import os
import threading
from concurrent.futures import ThreadPoolExecutor

os.environ['DATABASE_URL'] = 'sqlite:///./wallet_test.db'
os.environ['JWT_SECRET_KEY'] = 'test-only-secret-do-not-use-in-production'
os.environ['JWT_ALGORITHM'] = 'HS256'
os.environ['ACCESS_TOKEN_EXPIRE_MINUTES'] = '30'

from fastapi.testclient import TestClient
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
import pytest

from app.database import SessionLocal
from app.main import app
from app.models import LedgerEntry, User, Wallet
from app.services import WalletService

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


def test_list_wallets_returns_authenticated_users_wallet() -> None:
    with TestClient(app) as client:
        headers, user_id = login_headers(client)
        created = client.post('/wallets', json={'user_id': user_id}, headers=headers)
        response = client.get('/wallets', headers=headers)

    assert created.status_code == 201
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]['id'] == created.json()['id']
    assert response.json()[0]['user_id'] == user_id


def test_list_wallets_returns_empty_list_when_user_has_no_wallet() -> None:
    with TestClient(app) as client:
        headers, _ = login_headers(client)
        response = client.get('/wallets', headers=headers)

    assert response.status_code == 200
    assert response.json() == []


def test_list_wallets_pagination_applies_limit_and_offset() -> None:
    with TestClient(app) as client:
        headers, user_id = login_headers(client)
        created = client.post('/wallets', json={'user_id': user_id}, headers=headers)
        first_page = client.get('/wallets?limit=1&offset=0', headers=headers)
        next_page = client.get('/wallets?limit=1&offset=1', headers=headers)

    assert created.status_code == 201
    assert first_page.status_code == 200
    assert [wallet['id'] for wallet in first_page.json()] == [created.json()['id']]
    assert next_page.status_code == 200
    assert next_page.json() == []


def test_list_wallets_is_isolated_between_users() -> None:
    with TestClient(app) as client:
        first_headers, first_user_id = login_headers(client)
        first_wallet = client.post(
            '/wallets', json={'user_id': first_user_id}, headers=first_headers
        )

        second_registered = client.post(
            '/auth/register',
            json={'username': 'phase1-second-user', 'password': TEST_PASSWORD},
        )
        assert second_registered.status_code == 201
        second_login = client.post(
            '/auth/login',
            json={'username': 'phase1-second-user', 'password': TEST_PASSWORD},
        )
        assert second_login.status_code == 200
        second_headers = {
            'Authorization': f"Bearer {second_login.json()['access_token']}"
        }
        second_wallet = client.post(
            '/wallets',
            json={'user_id': second_registered.json()['id']},
            headers=second_headers,
        )

        first_list = client.get('/wallets', headers=first_headers)
        second_list = client.get('/wallets', headers=second_headers)

    assert first_wallet.status_code == 201
    assert second_wallet.status_code == 201
    assert first_list.status_code == 200
    assert second_list.status_code == 200
    assert [wallet['id'] for wallet in first_list.json()] == [first_wallet.json()['id']]
    assert [wallet['id'] for wallet in second_list.json()] == [second_wallet.json()['id']]


def test_concurrent_duplicate_wallet_creation_returns_one_conflict() -> None:
    with TestClient(app) as client:
        headers, user_id = login_headers(client)
        start = threading.Barrier(2)

        def create_wallet_request() -> int:
            start.wait(timeout=10)
            return client.post(
                '/wallets', json={'user_id': user_id}, headers=headers
            ).status_code

        with ThreadPoolExecutor(max_workers=2) as executor:
            statuses = list(executor.map(lambda _: create_wallet_request(), range(2)))

        wallets = client.get('/wallets', headers=headers)

    assert sorted(statuses) == [201, 409]
    assert wallets.status_code == 200
    assert len(wallets.json()) == 1


def test_unrelated_integrity_error_is_rolled_back_and_not_mapped_to_conflict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = SessionLocal()
    rollback_called = False

    def fail_commit() -> None:
        raise IntegrityError("INSERT", {}, Exception("unrelated constraint failure"))

    def record_rollback() -> None:
        nonlocal rollback_called
        rollback_called = True

    monkeypatch.setattr(db, 'commit', fail_commit)
    monkeypatch.setattr(db, 'rollback', record_rollback)
    try:
        with pytest.raises(IntegrityError, match='unrelated constraint failure'):
            WalletService.create_wallet(db, user_id='integrity-error-test')
    finally:
        db.close()

    assert rollback_called

import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

os.environ['DATABASE_URL'] = 'sqlite:///./wallet_test.db'
os.environ['JWT_SECRET_KEY'] = 'test-only-secret-do-not-use-in-production'
os.environ['JWT_ALGORITHM'] = 'HS256'
os.environ['ACCESS_TOKEN_EXPIRE_MINUTES'] = '30'

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.auth import create_access_token
from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.models import LedgerEntry, User, Wallet

TEST_USERNAME = 'phase3-test-user'
TEST_PASSWORD = 'phase3-test-password'


def setup_function() -> None:
    with SessionLocal() as db:
        db.execute(delete(LedgerEntry))
        db.execute(delete(Wallet))
        db.execute(delete(User))
        db.commit()


def _register(client: TestClient, username: str = TEST_USERNAME) -> dict:
    response = client.post('/auth/register', json={'username': username, 'password': TEST_PASSWORD})
    assert response.status_code == 201
    return response.json()


def _login(client: TestClient, username: str = TEST_USERNAME) -> dict[str, str]:
    response = client.post('/auth/login', json={'username': username, 'password': TEST_PASSWORD})
    assert response.status_code == 200
    return {'Authorization': f"Bearer {response.json()['access_token']}"}


def test_registration_success_and_password_is_hashed() -> None:
    with TestClient(app) as client:
        response = client.post('/auth/register', json={'username': TEST_USERNAME, 'password': TEST_PASSWORD})
    assert response.status_code == 201
    assert response.json()['username'] == TEST_USERNAME
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == TEST_USERNAME).one()
        assert user.password_hash != TEST_PASSWORD
        assert user.password_hash.startswith('scrypt$')


def test_duplicate_registration_returns_409() -> None:
    with TestClient(app) as client:
        _register(client)
        response = client.post('/auth/register', json={'username': TEST_USERNAME, 'password': TEST_PASSWORD})
    assert response.status_code == 409


def test_login_returns_jwt_with_database_user_id() -> None:
    with TestClient(app) as client:
        user = _register(client)
        response = client.post('/auth/login', json={'username': TEST_USERNAME, 'password': TEST_PASSWORD})
    assert response.status_code == 200
    assert response.json()['token_type'] == 'bearer'
    assert response.json()['expires_in'] == 1800
    claims = jwt.decode(response.json()['access_token'], settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    assert claims['sub'] == user['id']


def test_login_wrong_password_returns_401() -> None:
    with TestClient(app) as client:
        _register(client)
        response = client.post('/auth/login', json={'username': TEST_USERNAME, 'password': 'wrong-password'})
    assert response.status_code == 401


def test_missing_authorization_header_returns_401() -> None:
    with TestClient(app) as client:
        response = client.get('/wallets')
    assert response.status_code == 401


def test_invalid_jwt_returns_401() -> None:
    with TestClient(app) as client:
        response = client.get('/wallets', headers={'Authorization': 'Bearer not-a-valid-jwt'})
    assert response.status_code == 401


def test_expired_jwt_returns_401() -> None:
    with TestClient(app) as client:
        user = _register(client)
        expired_token = jwt.encode({'sub': user['id'], 'exp': datetime.now(timezone.utc) - timedelta(seconds=1)}, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        response = client.get('/wallets', headers={'Authorization': f'Bearer {expired_token}'})
    assert response.status_code == 401


def test_wallet_creation_uses_authenticated_user_id() -> None:
    with TestClient(app) as client:
        user = _register(client)
        headers = _login(client)
        response = client.post('/wallets', json={'user_id': user['id']}, headers=headers)
    assert response.status_code == 201
    assert response.json()['user_id'] == user['id']


def test_user_cannot_create_wallet_for_another_user_id() -> None:
    with TestClient(app) as client:
        _register(client)
        headers = _login(client)
        response = client.post('/wallets', json={'user_id': str(uuid.uuid4())}, headers=headers)
    assert response.status_code == 403


def test_user_can_access_own_wallet() -> None:
    with TestClient(app) as client:
        user = _register(client)
        headers = _login(client)
        created = client.post('/wallets', json={'user_id': user['id']}, headers=headers)
        response = client.get(f"/wallets/{created.json()['id']}/balance", headers=headers)
    assert created.status_code == 201
    assert response.status_code == 200


def test_user_cannot_access_another_users_wallet() -> None:
    with TestClient(app) as client:
        owner = _register(client, 'wallet-owner')
        owner_headers = _login(client, 'wallet-owner')
        created = client.post('/wallets', json={'user_id': owner['id']}, headers=owner_headers)
        _register(client, TEST_USERNAME)
        other_headers = _login(client, TEST_USERNAME)
        response = client.get(f"/wallets/{created.json()['id']}/balance", headers=other_headers)
    assert response.status_code == 403


def test_user_cannot_request_another_users_wallet_by_user_id() -> None:
    with TestClient(app) as client:
        _register(client)
        _register(client, 'another-user')
        headers = _login(client)
        response = client.get('/wallets/users/another-user', headers=headers)
    assert response.status_code == 403


def test_user_cannot_credit_or_debit_another_users_wallet() -> None:
    with TestClient(app) as client:
        owner = _register(client, 'wallet-owner')
        owner_headers = _login(client, 'wallet-owner')
        created = client.post('/wallets', json={'user_id': owner['id']}, headers=owner_headers)
        wallet_id = created.json()['id']
        client.post(f'/wallets/{wallet_id}/credit', json={'amount': '100.00'}, headers=owner_headers)
        _register(client, TEST_USERNAME)
        other_headers = _login(client, TEST_USERNAME)
        debit = client.post(f'/wallets/{wallet_id}/debit', json={'amount': '10.00'}, headers=other_headers)
        credit = client.post(f'/wallets/{wallet_id}/credit', json={'amount': '10.00'}, headers=other_headers)
    assert debit.status_code == 403
    assert credit.status_code == 403
    with SessionLocal() as db:
        wallet_uuid = uuid.UUID(wallet_id)
        wallet = db.query(Wallet).filter(Wallet.id == wallet_uuid).first()
        assert wallet is not None
        assert wallet.balance == Decimal('100.0000')
        assert db.query(LedgerEntry).filter(LedgerEntry.wallet_id == wallet_uuid).count() == 1

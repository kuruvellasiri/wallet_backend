# Wallet Service API

A FastAPI wallet and ledger service backed by PostgreSQL. Wallet endpoints require a JWT Bearer token and check that the token belongs to the wallet owner.

## Run locally on Windows

1. Install Python 3.10 or newer and PostgreSQL.
2. Create a PostgreSQL role and database, create and activate a virtual environment, and install the packages in requirements.txt.
3. Copy .env.example to .env. Set DATABASE_URL and the JWT settings. The .env file is ignored by Git.
4. Generate a strong signing secret locally with Python: python -c "import secrets; print(secrets.token_urlsafe(48))". Put it in JWT_SECRET_KEY. Do not commit .env.
5. Start the server with uvicorn app.main:app --reload.

Open http://127.0.0.1:8000/docs to try the endpoints. SQLAlchemy creates missing tables when the app starts. Use a migration tool such as Alembic for managed production schema changes.

## Authentication

Users register in PostgreSQL. Registration stores a salted scrypt password hash; the plaintext password is never stored. Login looks up the registered user, verifies the password, and returns a signed JWT whose sub claim is that user's UUID.

Configure DATABASE_URL, JWT_SECRET_KEY, JWT_ALGORITHM=HS256, and ACCESS_TOKEN_EXPIRE_MINUTES in .env.

Register using POST /auth/register with a JSON body such as:
{"username": "user_2", "password": "choose-a-strong-password"}

Then login using POST /auth/login with the same credentials. The response contains an access_token. Send it with each wallet request in the Authorization: Bearer <JWT> header.

For POST /wallets, send the registered user's UUID as user_id. The backend checks it against the JWT identity; a different value gets 403. A missing, invalid, or expired token gets 401. A valid token used against another user's wallet gets 403. Ownership checks cover wallet creation, lookup, balance, ledger, credit, and debit.

## Wallet endpoints

All wallet endpoints require a Bearer token.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | /wallets | Create a wallet for the authenticated user |
| GET | /wallets | List the authenticated user's wallets |
| GET | /wallets/users/{user_id} | Get the authenticated user's wallet |
| POST | /wallets/{wallet_id}/credit | Credit a positive amount |
| POST | /wallets/{wallet_id}/debit | Debit a positive amount |
| GET | /wallets/{wallet_id}/balance | Read the wallet balance |
| GET | /wallets/{wallet_id}/ledger | Read paginated ledger history |

Credit and debit request bodies use a decimal amount and optional description, for example {"amount": "12.50", "description": "Top up"}.

## How wallet changes stay consistent

Credit and debit services lock the wallet row with SELECT ... FOR UPDATE, then update the balance and insert the ledger row in one database transaction. PostgreSQL serializes competing changes to the same wallet. The database also checks that the balance is non-negative and ledger amounts are positive.

## Tests

Run the local API tests with python -m pytest -q.

The HTTP concurrency test targets a separately running PostgreSQL-backed API. Set RUN_CONCURRENCY_INTEGRATION=1 before running it; it registers a unique temporary account through the API. SQLite does not provide PostgreSQL row-level locking, so it cannot prove the Phase 2 concurrency behavior.

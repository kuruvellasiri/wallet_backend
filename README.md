# Wallet Service API

A beginner-friendly FastAPI service for creating wallets, crediting and debiting
balances, and reading a paginated transaction ledger. Wallet and ledger rows are
stored in PostgreSQL through SQLAlchemy.

## Run locally on Windows

1. Install Python 3.10 or newer and PostgreSQL.
2. Create a database and a PostgreSQL role (replace the example password):

   ```sql
   CREATE USER wallet_user WITH PASSWORD 'choose-a-local-password';
   CREATE DATABASE wallet_db OWNER wallet_user;
   ```

3. Create and activate a virtual environment, then install dependencies:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

4. Copy `.env.example` to `.env` and set `DATABASE_URL` to your local PostgreSQL
   username, password, host, port, and database. `.env` is ignored by Git.
5. Start the development server:

   ```powershell
   uvicorn app.main:app --reload
   ```

   Open `http://127.0.0.1:8000/docs` to try the endpoints.

Tables are created from the SQLAlchemy models when the application starts.
For a production deployment, use a migration tool such as Alembic to evolve the
schema rather than relying on `create_all`.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/wallets` | Create one wallet for a `user_id` |
| `POST` | `/wallets/{wallet_id}/credits` | Credit a positive amount |
| `POST` | `/wallets/{wallet_id}/debits` | Debit a positive amount |
| `GET` | `/wallets/{wallet_id}/balance` | Read the current balance |
| `GET` | `/wallets/{wallet_id}/transactions?limit=50&offset=0` | Read ledger history |

Credit and debit request bodies accept `amount` as a decimal string and an
optional `description`, for example `{"amount": "12.50", "description": "Top up"}`.

## Request flow

1. `app/routes.py` validates the HTTP request and obtains a SQLAlchemy session
   through the `get_db` dependency.
2. The route calls a focused function in `app/services.py`; routes do not decide
   wallet business rules.
3. The service loads and, for a money change, locks the wallet row with
   `SELECT ... FOR UPDATE`. Inside one database transaction it changes the
   balance and inserts a ledger row containing the resulting balance.
4. SQLAlchemy commits when the transaction block succeeds, or rolls it back on
   failure. Database constraints independently reject duplicate user wallets,
   negative balances, and non-positive ledger amounts.
5. The route returns a Pydantic response. Expected service errors are converted
   into HTTP status codes by handlers in `app/main.py`.

## Tests

The tests use a local SQLite file so the API behavior can be checked without a
running PostgreSQL server:

```powershell
pytest
```

SQLite does not implement PostgreSQL row-level locking; concurrency safety for
credit/debit operations relies on PostgreSQL's `FOR UPDATE` behavior and should
be exercised against PostgreSQL before deployment.

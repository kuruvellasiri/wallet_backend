import uuid

from typing import Annotated, List

from fastapi import (
    APIRouter,
    Depends,
    Query,
    status,
)

from sqlalchemy.orm import Session

from app.database import get_db

from app.services import WalletService

from app.schemas import (
    WalletCreate,
    WalletResponse,
    WalletBalanceResponse,
    TransactionRequest,
    LedgerEntryResponse,
    LedgerHistoryResponse,
)


router = APIRouter(
    prefix="/wallets",
    tags=["Wallets"],
)


DBDep = Annotated[
    Session,
    Depends(get_db)
]


# ---------------------------------
# Create Wallet
# ---------------------------------

@router.post(
    "",
    response_model=WalletResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_wallet(
    payload: WalletCreate,
    db: DBDep,
):

    return WalletService.create_wallet(
        db,
        user_id=payload.user_id,
        currency=payload.currency or "USD",
    )


# ---------------------------------
# List Wallets
# ---------------------------------

@router.get(
    "",
    response_model=List[WalletResponse],
)
def list_wallets(
    db: DBDep,

    limit: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 50,

    offset: Annotated[
        int,
        Query(ge=0),
    ] = 0,
):

    return WalletService.get_all_wallets(
        db,
        limit=limit,
        offset=offset,
    )


# ---------------------------------
# Get Wallet By User
# ---------------------------------

@router.get(
    "/users/{user_id}",
    response_model=WalletResponse,
)
def get_wallet_by_user(
    user_id: str,
    db: DBDep,
):

    return WalletService.get_wallet_by_user_id(
        db,
        user_id=user_id,
    )


# ---------------------------------
# Credit
# ---------------------------------

@router.post(
    "/{wallet_id}/credit",
    response_model=LedgerEntryResponse,
)
def credit_wallet(
    wallet_id: uuid.UUID,
    payload: TransactionRequest,
    db: DBDep,
):

    _, ledger_entry = WalletService.credit_wallet(
        db,
        wallet_id=wallet_id,
        amount=payload.amount,
        description=payload.description,
    )

    return ledger_entry


# ---------------------------------
# Debit
# ---------------------------------

@router.post(
    "/{wallet_id}/debit",
    response_model=LedgerEntryResponse,
)
def debit_wallet(
    wallet_id: uuid.UUID,
    payload: TransactionRequest,
    db: DBDep,
):

    _, ledger_entry = WalletService.debit_wallet(
        db,
        wallet_id=wallet_id,
        amount=payload.amount,
        description=payload.description,
    )

    return ledger_entry


# ---------------------------------
# Get Balance
# ---------------------------------

@router.get(
    "/{wallet_id}/balance",
    response_model=WalletBalanceResponse,
)
def get_wallet_balance(
    wallet_id: uuid.UUID,
    db: DBDep,
):

    wallet = WalletService.get_wallet_by_id(
        db,
        wallet_id=wallet_id,
    )

    return WalletBalanceResponse(
        wallet_id=wallet.id,
        user_id=wallet.user_id,
        balance=wallet.balance,
        currency=wallet.currency,
        updated_at=wallet.updated_at,
    )


# ---------------------------------
# Get Ledger
# ---------------------------------

@router.get(
    "/{wallet_id}/ledger",
    response_model=LedgerHistoryResponse,
)
def get_wallet_ledger(
    wallet_id: uuid.UUID,
    db: DBDep,

    limit: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 50,

    offset: Annotated[
        int,
        Query(ge=0),
    ] = 0,
):

    total, entries = WalletService.get_ledger_history(
        db,
        wallet_id=wallet_id,
        limit=limit,
        offset=offset,
    )

    return LedgerHistoryResponse(
        wallet_id=wallet_id,
        total_entries=total,
        entries=entries,
    )
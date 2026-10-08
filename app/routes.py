import uuid

from typing import Annotated, List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)

from sqlalchemy.orm import Session

from app.database import get_db

from app.services import WalletService
from app.auth import AuthenticatedUser, get_current_user
from app.models import Wallet

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

CurrentUserDep = Annotated[
    AuthenticatedUser,
    Depends(get_current_user),
]


def _get_owned_wallet(
    db: Session,
    wallet_id: uuid.UUID,
    current_user: AuthenticatedUser,
) -> Wallet:
    wallet = WalletService.get_wallet_by_id(db, wallet_id)
    if wallet.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this wallet",
        )
    return wallet


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
    current_user: CurrentUserDep,
):

    if payload.user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A wallet can only be created for the authenticated user",
        )

    return WalletService.create_wallet(
        db,
        user_id=current_user.user_id,
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
    current_user: CurrentUserDep,

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
        user_id=current_user.user_id,
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
    current_user: CurrentUserDep,
):

    if user_id != current_user.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this user's wallet",
        )

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
    current_user: CurrentUserDep,
):

    _get_owned_wallet(db, wallet_id, current_user)

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
    current_user: CurrentUserDep,
):

    _get_owned_wallet(db, wallet_id, current_user)

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
    current_user: CurrentUserDep,
):

    wallet = _get_owned_wallet(db, wallet_id, current_user)

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
    current_user: CurrentUserDep,

    limit: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 50,

    offset: Annotated[
        int,
        Query(ge=0),
    ] = 0,
):

    _get_owned_wallet(db, wallet_id, current_user)

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

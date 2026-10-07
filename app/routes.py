from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Wallet, Ledger
from .schemas import WalletCreate, MoneyRequest, WalletResponse

router = APIRouter(prefix="/wallets", tags=["Wallet"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/{user_id}", response_model=WalletResponse)
def create_wallet(user_id: int, db: Session = Depends(get_db)):
    
    existing_wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()

    if existing_wallet:
        raise HTTPException(status_code=400, detail="Wallet already exists")

    wallet = Wallet(user_id=user_id, balance=0)

    db.add(wallet)
    db.commit()
    db.refresh(wallet)

    return wallet


@router.post("/{user_id}/credit")
def credit_wallet(
    user_id: int,
    request: MoneyRequest,
    db: Session = Depends(get_db)
):
    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    wallet.balance += request.amount

    ledger = Ledger(
        wallet_id=wallet.id,
        transaction_type="CREDIT",
        amount=request.amount
    )

    db.add(ledger)
    db.commit()
    db.refresh(wallet)

    return {
        "message": "Money credited successfully",
        "balance": wallet.balance
    }


@router.post("/{user_id}/debit")
def debit_wallet(
    user_id: int,
    request: MoneyRequest,
    db: Session = Depends(get_db)
):
    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    if wallet.balance < request.amount:
        raise HTTPException(
            status_code=400,
            detail="Insufficient balance"
        )

    wallet.balance -= request.amount

    ledger = Ledger(
        wallet_id=wallet.id,
        transaction_type="DEBIT",
        amount=request.amount
    )

    db.add(ledger)
    db.commit()
    db.refresh(wallet)

    return {
        "message": "Money debited successfully",
        "balance": wallet.balance
    }


@router.get("/{user_id}/balance")
def get_balance(user_id: int, db: Session = Depends(get_db)):
    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    return {
        "user_id": user_id,
        "balance": wallet.balance
    }


@router.get("/{user_id}/transactions")
def get_transactions(user_id: int, db: Session = Depends(get_db)):
    wallet = db.query(Wallet).filter(Wallet.user_id == user_id).first()

    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    transactions = (
        db.query(Ledger)
        .filter(Ledger.wallet_id == wallet.id)
        .order_by(Ledger.id.desc())
        .all()
    )

    return transactions
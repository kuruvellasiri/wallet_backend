import uuid

from decimal import Decimal
from typing import List, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from fastapi import HTTPException, status

from app.models import (
    Wallet,
    LedgerEntry,
    LedgerOperation,
)


class WalletService:

    # ---------------------------------
    # Create Wallet
    # ---------------------------------

    @staticmethod
    def create_wallet(
        db: Session,
        user_id: str,
        currency: str = "USD",
    ) -> Wallet:

        existing = (
            db.query(Wallet)
            .filter(Wallet.user_id == user_id)
            .first()
        )

        if existing:

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Wallet already exists for user_id '{user_id}'",
            )

        wallet = Wallet(
            user_id=user_id,
            balance=Decimal("0.0000"),
            currency=currency.upper(),
        )

        db.add(wallet)

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            if WalletService._is_duplicate_wallet_user_error(exc):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="A wallet already exists for this user",
                ) from exc
            raise

        db.refresh(wallet)

        return wallet

    @staticmethod
    def _is_duplicate_wallet_user_error(exc: IntegrityError) -> bool:
        """Return True only for the wallets.user_id uniqueness violation."""
        original = exc.orig

        # PostgreSQL reports the exact violated constraint through psycopg.
        diag = getattr(original, "diag", None)
        constraint_name = getattr(diag, "constraint_name", None)
        sqlstate = getattr(original, "pgcode", None) or getattr(
            original, "sqlstate", None
        )
        unique_user_id_indexes = {
            index.name
            for index in Wallet.__table__.indexes
            if index.unique and list(index.columns.keys()) == ["user_id"]
        }
        if (
            sqlstate == "23505"
            and constraint_name in unique_user_id_indexes | {"wallets_user_id_key"}
        ):
            return True

        # SQLite is used by the unit tests and reports the affected columns.
        message = str(original)
        return message == "UNIQUE constraint failed: wallets.user_id"

    # ---------------------------------
    # Get Wallet By ID
    # ---------------------------------

    @staticmethod
    def get_wallet_by_id(
        db: Session,
        wallet_id: uuid.UUID,
    ) -> Wallet:

        wallet = (
            db.query(Wallet)
            .filter(Wallet.id == wallet_id)
            .first()
        )

        if not wallet:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Wallet with id '{wallet_id}' not found",
            )

        return wallet

    # ---------------------------------
    # Get Wallet By User ID
    # ---------------------------------

    @staticmethod
    def get_wallet_by_user_id(
        db: Session,
        user_id: str,
    ) -> Wallet:

        wallet = (
            db.query(Wallet)
            .filter(Wallet.user_id == user_id)
            .first()
        )

        if not wallet:

            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Wallet for user_id '{user_id}' not found",
            )

        return wallet

    # ---------------------------------
    # Get All Wallets
    # ---------------------------------

    @staticmethod
    def get_all_wallets(
        db: Session,
        user_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Wallet]:

        return (
            db.query(Wallet)
            .filter(Wallet.user_id == user_id)
            .order_by(Wallet.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

    # ---------------------------------
    # Credit Wallet
    # ---------------------------------

    @staticmethod
    def credit_wallet(
        db: Session,
        wallet_id: uuid.UUID,
        amount: Decimal,
        description: str | None = None,
    ) -> Tuple[Wallet, LedgerEntry]:

        if amount <= 0:

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Credit amount must be strictly greater than 0",
            )

        try:

            wallet = (
                db.query(Wallet)
                .filter(Wallet.id == wallet_id)
                .with_for_update()
                .first()
            )

            if not wallet:

                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Wallet with id '{wallet_id}' not found",
                )

            # Add money
            new_balance = wallet.balance + amount

            wallet.balance = new_balance

            # Create ledger record
            ledger_entry = LedgerEntry(
                wallet_id=wallet.id,
                operation_type=LedgerOperation.CREDIT,
                amount=amount,
                balance_after=new_balance,
                description=description,
            )

            db.add(ledger_entry)

            # Save both operations atomically
            db.commit()

            db.refresh(wallet)

            db.refresh(ledger_entry)

            return wallet, ledger_entry

        except HTTPException:

            db.rollback()

            raise

        except Exception:

            db.rollback()

            raise

    # ---------------------------------
    # Debit Wallet
    # ---------------------------------

    @staticmethod
    def debit_wallet(
        db: Session,
        wallet_id: uuid.UUID,
        amount: Decimal,
        description: str | None = None,
    ) -> Tuple[Wallet, LedgerEntry]:

        if amount <= 0:

            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debit amount must be strictly greater than 0",
            )

        try:

            wallet = (
                db.query(Wallet)
                .filter(Wallet.id == wallet_id)
                .with_for_update()
                .first()
            )

            if not wallet:

                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Wallet with id '{wallet_id}' not found",
                )

            # Prevent negative balance
            if wallet.balance < amount:

                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=(
                        f"Insufficient funds: current balance is "
                        f"{wallet.balance}, attempted to debit {amount}"
                    ),
                )

            # Subtract money
            new_balance = wallet.balance - amount

            wallet.balance = new_balance

            # Create ledger record
            ledger_entry = LedgerEntry(
                wallet_id=wallet.id,
                operation_type=LedgerOperation.DEBIT,
                amount=amount,
                balance_after=new_balance,
                description=description,
            )

            db.add(ledger_entry)

            # Save both operations
            db.commit()

            db.refresh(wallet)

            db.refresh(ledger_entry)

            return wallet, ledger_entry

        except HTTPException:

            db.rollback()

            raise

        except Exception:

            db.rollback()

            raise

    # ---------------------------------
    # Get Ledger
    # ---------------------------------

    @staticmethod
    def get_ledger_history(
        db: Session,
        wallet_id: uuid.UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[int, List[LedgerEntry]]:

        # First make sure wallet exists
        WalletService.get_wallet_by_id(
            db,
            wallet_id,
        )

        total_count = (
            db.query(func.count(LedgerEntry.id))
            .filter(
                LedgerEntry.wallet_id == wallet_id
            )
            .scalar()
        )

        entries = (
            db.query(LedgerEntry)
            .filter(
                LedgerEntry.wallet_id == wallet_id
            )
            .order_by(
                LedgerEntry.created_at.desc()
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

        return total_count, entries

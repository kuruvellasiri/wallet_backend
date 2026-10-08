import uuid

from decimal import Decimal
from datetime import datetime
from typing import Optional, List

from pydantic import (
    BaseModel,
    Field,
    ConfigDict,
)

from app.models import LedgerOperation


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=256)


class RegisterRequest(LoginRequest):
    """Credentials used to create a new account."""


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# -------------------------
# Wallet Schemas
# -------------------------

class WalletCreate(BaseModel):

    user_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique user identifier",
    )

    currency: Optional[str] = Field(
        "USD",
        min_length=3,
        max_length=10,
        description="Currency code",
    )


class WalletResponse(BaseModel):

    id: uuid.UUID

    user_id: str

    balance: Decimal

    currency: str

    created_at: datetime

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class WalletBalanceResponse(BaseModel):

    wallet_id: uuid.UUID

    user_id: str

    balance: Decimal

    currency: str

    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


# -------------------------
# Transaction Schemas
# -------------------------

class TransactionRequest(BaseModel):

    amount: Decimal = Field(
        ...,
        gt=0,
        decimal_places=4,
        description="Transaction amount",
    )

    description: Optional[str] = Field(
        None,
        max_length=255,
        description="Optional transaction description",
    )


class LedgerEntryResponse(BaseModel):

    id: uuid.UUID

    wallet_id: uuid.UUID

    operation_type: LedgerOperation

    amount: Decimal

    balance_after: Decimal

    description: Optional[str]

    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


class LedgerHistoryResponse(BaseModel):

    wallet_id: uuid.UUID

    total_entries: int

    entries: List[LedgerEntryResponse]

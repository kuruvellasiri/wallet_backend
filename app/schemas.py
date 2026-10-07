from pydantic import BaseModel, Field
from decimal import Decimal


class WalletCreate(BaseModel):
    user_id: int


class MoneyRequest(BaseModel):
    amount: Decimal = Field(gt=0)


class WalletResponse(BaseModel):
    id: int
    user_id: int
    balance: Decimal

    class Config:
        from_attributes = True
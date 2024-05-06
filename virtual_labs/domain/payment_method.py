from datetime import datetime
from typing import List

from pydantic import UUID4, BaseModel, ConfigDict, EmailStr, Field


class PaymentMethod(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    brand: str
    card_number: str
    cardholder_name: str
    cardholder_email: str
    expire_at: str

    created_at: datetime
    updated_at: datetime | None


class PaymentMethodsOut(BaseModel):
    virtual_lab_id: UUID4
    payment_methods: List[PaymentMethod]


class PaymentMethodOut(BaseModel):
    virtual_lab_id: UUID4
    payment_method: PaymentMethod


class PaymentMethodCreationBody(BaseModel):
    customerId: str
    name: str
    email: EmailStr
    expireAt: str = Field(
        min_length=7,
        max_length=7,
        pattern=r"^(0[1-9]|1[0-2])\/\d{4}$",
        description="Stripe expire date format: MM/YYYY",
        examples=["12/2024"],
    )
    paymentMethodId: str
    brand: str
    last4: str

from datetime import datetime
from typing import List

from pydantic import UUID4, BaseModel, ConfigDict, EmailStr


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


class SetupIntentOut(BaseModel):
    id: str
    client_secret: str
    customer_id: str


class PaymentMethodCreationBody(BaseModel):
    setupIntentId: str
    name: str
    email: EmailStr

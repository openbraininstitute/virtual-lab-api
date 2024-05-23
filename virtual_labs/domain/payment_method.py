from datetime import datetime
from typing import List, Literal, Optional

import stripe
from pydantic import UUID4, BaseModel, ConfigDict, EmailStr


class PaymentMethod(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID4
    brand: str
    card_number: str
    cardholder_name: str
    cardholder_email: str
    expire_at: str
    default: Optional[bool] = False

    created_at: datetime
    updated_at: datetime | None


class PaymentMethodsOut(BaseModel):
    virtual_lab_id: UUID4
    payment_methods: List[PaymentMethod]


class PaymentMethodOut(BaseModel):
    virtual_lab_id: UUID4
    payment_method: PaymentMethod


class StripePaymentOut(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    virtual_lab_id: UUID4
    status: Literal[
        "canceled",
        "processing",
        "requires_action",
        "requires_capture",
        "requires_confirmation",
        "requires_payment_method",
        "succeeded",
    ]
    next_action: stripe.PaymentIntent.NextAction
    cancellation_reason: Optional[
        Literal[
            "abandoned",
            "automatic",
            "duplicate",
            "failed_invoice",
            "fraudulent",
            "requested_by_customer",
            "void_invoice",
        ]
    ]


class VlabBalanceOut(BaseModel):
    virtual_lab_id: UUID4
    budget: float
    total_spent: float


class PaymentMethodDeletionOut(BaseModel):
    virtual_lab_id: UUID4
    payment_method_id: UUID4
    deleted: bool
    deleted_at: datetime


class SetupIntentOut(BaseModel):
    id: str
    client_secret: str
    customer_id: str


class PaymentMethodCreationBody(BaseModel):
    setupIntentId: str
    name: str
    email: EmailStr

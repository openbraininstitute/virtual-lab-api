from typing import TYPE_CHECKING, Dict, List, Literal, Optional, cast, overload
from uuid import UUID

import stripe
from loguru import logger
from stripe import (
    Customer,
    CustomerService,
    PaymentIntentService,
    SignatureVerificationError,
)
from stripe.tax import CalculationService

from virtual_labs.infrastructure.settings import settings
from virtual_labs.infrastructure.stripe.config import stripe_client

if TYPE_CHECKING:
    from virtual_labs.domain.billing import BillingAddress


_AddressTarget = Literal["customer_create", "customer_update", "tax_calculation"]

_AddressResult = (
    CustomerService.CreateParamsAddress
    | CustomerService.UpdateParamsAddress
    | CalculationService.CreateParamsCustomerDetailsAddress
)


@overload
def _build_stripe_address(
    address: "BillingAddress", target: Literal["customer_create"]
) -> CustomerService.CreateParamsAddress: ...


@overload
def _build_stripe_address(
    address: "BillingAddress", target: Literal["customer_update"]
) -> CustomerService.UpdateParamsAddress: ...


@overload
def _build_stripe_address(
    address: "BillingAddress", target: Literal["tax_calculation"]
) -> CalculationService.CreateParamsCustomerDetailsAddress: ...


def _build_stripe_address(
    address: "BillingAddress", target: _AddressTarget
) -> _AddressResult:
    """Convert a BillingAddress into the Stripe-typed dict for the given context.

    Uses @overload so each call site gets the exact return type it expects.
    """
    if target == "tax_calculation":
        result_tax = CalculationService.CreateParamsCustomerDetailsAddress(
            country=address.country or "",
        )
        if address.line1:
            result_tax["line1"] = address.line1
        if address.line2:
            result_tax["line2"] = address.line2
        if address.city:
            result_tax["city"] = address.city
        if address.state:
            result_tax["state"] = address.state
        if address.postal_code:
            result_tax["postal_code"] = address.postal_code
        return result_tax
    elif target == "customer_create":
        result_create = CustomerService.CreateParamsAddress()
        if address.line1:
            result_create["line1"] = address.line1
        if address.line2:
            result_create["line2"] = address.line2
        if address.city:
            result_create["city"] = address.city
        if address.state:
            result_create["state"] = address.state
        if address.postal_code:
            result_create["postal_code"] = address.postal_code
        if address.country:
            result_create["country"] = address.country
        return result_create
    else:
        result_update = CustomerService.UpdateParamsAddress()
        if address.line1:
            result_update["line1"] = address.line1
        if address.line2:
            result_update["line2"] = address.line2
        if address.city:
            result_update["city"] = address.city
        if address.state:
            result_update["state"] = address.state
        if address.postal_code:
            result_update["postal_code"] = address.postal_code
        if address.country:
            result_update["country"] = address.country
        return result_update


class StripeRepository:
    def __init__(self) -> None:
        """
        initialize the Stripe service
        """

        self.api_key = settings.STRIPE_SECRET_KEY
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        self.stripe = stripe_client

    async def construct_event(
        self, payload: bytes, signature: str
    ) -> Optional[stripe.Event]:
        """
        construct and verify a Stripe event from webhook payload.

        Args:
            payload: raw request body from webhook
            signature: stripe signature header

        Returns:
            Verified Stripe event or None if verification fails
        """

        if not self.webhook_secret or not signature:
            logger.error("Missing webhook secret or signature")
            return None

        try:
            # Type ignore for the untyped function call
            event = stripe.Webhook.construct_event(  # type: ignore
                payload=payload,
                sig_header=signature,
                secret=self.webhook_secret,
            )
            return cast(stripe.Event, event)
        except SignatureVerificationError as e:
            logger.error(f"Invalid signature: {str(e)}")
            return None
        except Exception as e:
            logger.exception(f"Error constructing event: {str(e)}")
            return None

    async def get_subscription(
        self, subscription_id: str
    ) -> Optional[stripe.Subscription]:
        """
        retrieve a subscription from Stripe.

        Args:
            subscription_id: stripe subscription id

        Returns:
            Subscription data or None if not found
        """

        try:
            subscription = await self.stripe.subscriptions.retrieve_async(
                subscription_id,
                params={
                    "expand": [
                        "default_payment_method",
                        "latest_invoice",
                        "items.data.price",
                    ],
                },
            )
            return subscription
        except Exception as e:
            logger.exception(
                f"Error retrieving subscription {subscription_id}: {str(e)}"
            )
            return None

    async def get_invoice(self, invoice_id: str) -> Optional[stripe.Invoice]:
        """
        retrieve an invoice from Stripe.

        Args:
            invoice_id: stripe invoice id

        Returns:
            invoice data or None if not found
        """

        try:
            invoice = await self.stripe.invoices.retrieve_async(invoice_id)
            return invoice
        except Exception as e:
            logger.exception(f"Error retrieving invoice {invoice_id}: {str(e)}")
            return None

    async def get_payment_intent(
        self, payment_intent_id: str
    ) -> Optional[stripe.PaymentIntent]:
        """
        retrieve a payment intent from Stripe.

        Args:
            payment_intent_id: stripe payment intent id

        Returns:
            Payment intent data or None if not found
        """

        try:
            payment_intent = await self.stripe.payment_intents.retrieve_async(
                payment_intent_id,
                params={"expand": ["payment_method", "latest_charge", "invoice"]},
            )
            return payment_intent
        except Exception as e:
            logger.warning(
                f"Error retrieving payment intent {payment_intent_id}: {str(e)}"
            )
            return None

    async def get_payment_method(self, payment_method_id: str) -> stripe.PaymentMethod:
        """
        Retrieve a payment method from Stripe.

        Args:
            payment_method_id: The ID of the payment method to retrieve

        Returns:
            The payment method details
        """
        try:
            payment_method = await self.stripe.payment_methods.retrieve_async(
                payment_method_id
            )
            return payment_method
        except Exception as e:
            logger.error(f"Error retrieving payment method: {str(e)}")
            raise

    async def get_charge(self, charge_id: str) -> Optional[stripe.Charge]:
        """
        retrieve a charge from Stripe.

        Args:
            charge_id: stripe charge id

        Returns:
            charge data or None if not found
        """

        try:
            charge = await self.stripe.charges.retrieve_async(charge_id)
            return charge
        except Exception as e:
            logger.exception(f"Error retrieving charge {charge_id}: {str(e)}")
            return None

    async def list_products(self, active: bool = True) -> List[stripe.Product]:
        """
        list products from Stripe.

        Args:
            active: whether to only return active products

        Returns:
            list of products
        """
        try:
            products = await self.stripe.products.list_async({"active": active})
            return products.data
        except Exception as e:
            logger.exception(f"Error listing products: {str(e)}")
            return []

    async def list_prices(
        self, product_id: str, active: bool = True
    ) -> List[stripe.Price]:
        """
        list prices for a product from Stripe.

        Args:
            product_id:  Stripe product id
            active: whether to only return active prices

        Returns:
            list of prices
        """
        try:
            # Fix the parameter passing format
            prices = await self.stripe.prices.list_async(
                params={"product": product_id, "active": active}
            )
            return prices.data
        except Exception as e:
            logger.exception(f"Error listing prices for product {product_id}: {str(e)}")
            return []

    async def create_subscription(
        self,
        customer_id: str,
        price_id: str,
        payment_method_id: str,
        discount_id: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        automatic_tax_enabled: bool = False,
        *,
        idempotency_key: Optional[str] = None,
    ) -> Optional[stripe.Subscription]:
        """
        create a subscription in Stripe.

        Args:
            customer_id: stripe customer id
            price_id: stripe price id
            payment_method_id: stripe payment method id
            metadata: optional metadata for the subscription

        Returns:
            the created subscription
        """
        try:
            # set the payment method as the default for the customer
            await self.stripe.payment_methods.attach_async(
                payment_method_id,
                params={
                    "customer": customer_id,
                },
            )

            await self.stripe.customers.update_async(
                customer_id,
                params={
                    "invoice_settings": {
                        "default_payment_method": payment_method_id,
                    }
                },
            )

            # `idempotency_key` makes a retry of this exact create
            # return the same subscription rather than minting a
            # duplicate. Caller derives a deterministic key from
            # (user, tier, interval, attempt) so legitimate retries
            # converge but distinct user actions don't collide.
            create_kwargs: Dict[str, stripe.RequestOptions] = {}
            if idempotency_key:
                create_kwargs["options"] = stripe.RequestOptions(
                    idempotency_key=idempotency_key
                )
            subscription = await self.stripe.subscriptions.create_async(
                params={
                    "customer": customer_id,
                    "default_payment_method": payment_method_id,
                    "payment_behavior": "error_if_incomplete",  # NOTE: this important to not create stale subscription
                    "items": [
                        {
                            "price": price_id,
                        }
                    ],
                    "collection_method": "charge_automatically",  # NOTE: this is to charge the user at creation time
                    "metadata": metadata or {},
                    "automatic_tax": {"enabled": automatic_tax_enabled},
                    "payment_settings": {
                        "save_default_payment_method": "on_subscription"
                    },
                    "discounts": [
                        {
                            "coupon": discount_id,
                        }
                    ]
                    if discount_id
                    else "",
                    "description": "Creating subscription",
                },
                **create_kwargs,
            )
            return subscription
        except Exception as e:
            logger.exception(
                f"Error creating subscription for customer {customer_id}: {str(e)}"
            )
            raise

    async def cancel_subscription(
        self,
        subscription_id: str,
        *,
        cancel_immediately: bool = False,
    ) -> stripe.Subscription:
        """Cancel a Stripe subscription, immediately or at period end.

        `cancel_at_period_end=True` is naturally idempotent: calling
        it twice sets the same flag with no extra charge or state
        churn, so no idempotency key is needed.
        """
        try:
            if cancel_immediately:
                return await self.stripe.subscriptions.cancel_async(subscription_id)
            return await self.stripe.subscriptions.update_async(
                subscription_id, params={"cancel_at_period_end": True}
            )
        except stripe.StripeError:
            logger.exception(f"Error canceling Stripe subscription {subscription_id}")
            raise

    async def create_customer(
        self,
        user_id: UUID,
        email: str,
        name: Optional[str] = None,
        address: Optional["BillingAddress"] = None,
        validate_tax_location: bool = False,
        *,
        idempotency_key: Optional[str] = None,
    ) -> Optional[stripe.Customer]:
        """
        create a new stripe customer.

        Args:
            user_id: The user's id
            email: The customer's email address
            name: The customer's name (optional)
        Returns:
            The created Stripe customer object or None if creation failed
        """
        try:
            customer_data = stripe.Customer.CreateParams(
                name=str(name),
                email=str(email),
                metadata={
                    "user_id": str(user_id),
                    "email": str(email),
                    "name": str(name),
                },
            )
            if address is not None:
                customer_data["address"] = _build_stripe_address(
                    address, "customer_create"
                )
            if validate_tax_location:
                customer_data["tax"] = {"validate_location": "immediately"}
                customer_data["expand"] = ["tax"]

            # Idempotency on customer create — caller derives a key
            # from `user_id` so retries return the same customer.
            create_kwargs: Dict[str, stripe.RequestOptions] = {}
            if idempotency_key:
                create_kwargs["options"] = stripe.RequestOptions(
                    idempotency_key=idempotency_key
                )
            customer = await self.stripe.customers.create_async(
                customer_data, **create_kwargs
            )
            return customer
        except stripe.StripeError as e:
            logger.error(f"Failed to create Stripe customer: {str(e)}")
            if validate_tax_location:
                raise
            return None

    async def create_payment_intent(
        self,
        amount: int,
        currency: str,
        customer_id: str,
        payment_method_id: str,
        metadata: Optional[Dict[str, str]] = None,
        tax_calculation_id: Optional[str] = None,
        *,
        idempotency_key: Optional[str] = None,
    ) -> stripe.PaymentIntent:
        """
        create a payment intent in Stripe.

        Args:
            amount: Amount to charge in cents
            currency: Currency code (e.g., 'usd')
            customer_id: Stripe customer ID
            payment_method_id: Stripe payment method ID
            metadata: Optional metadata for the payment

        Returns:
            The created payment intent
        """
        try:
            params = PaymentIntentService.CreateParams(
                amount=amount,
                currency=currency,
                customer=customer_id,
                payment_method=payment_method_id,
                metadata=metadata or {},
                confirm=True,
                description="Adding credit",
                return_url=f"{settings.DEPLOYMENT_NAMESPACE}/app/virtual-lab/sync",
            )
            if tax_calculation_id:
                params["metadata"] = {
                    **(metadata or {}),
                    "tax_calculation": tax_calculation_id,
                }

            create_kwargs: Dict[str, stripe.RequestOptions] = {}
            if idempotency_key:
                create_kwargs["options"] = stripe.RequestOptions(
                    idempotency_key=idempotency_key
                )
            payment_intent = await self.stripe.payment_intents.create_async(
                params=params,
                **create_kwargs,
            )
            return payment_intent
        except Exception as e:
            logger.error(f"Error creating payment intent: {str(e)}")
            raise

    async def get_customer(self, customer_id: str) -> Optional[stripe.Customer]:
        """
        Retrieve a Stripe customer by customer ID.

        Args:
            customer_id: The Stripe customer ID

        Returns:
            Stripe customer object if found, None otherwise
        """
        try:
            customer = await self.stripe.customers.retrieve_async(customer=customer_id)
            return customer
        except Exception as e:
            logger.exception(f"Error retrieving customer {customer_id}: {str(e)}")
            return None

    async def update_customer(
        self,
        customer_id: str,
        email: Optional[str] = None,
        name: Optional[str] = None,
        address: Optional["BillingAddress"] = None,
        validate_tax_location: bool = False,
    ) -> Optional[Customer]:
        """
        Update a Stripe customer.

        Args:
            customer_id: The Stripe customer ID to update
            email: New email address for the customer
            name: New name for the customer

        Returns:
            Updated Stripe customer object or None if update failed
        """
        try:
            update_params: CustomerService.UpdateParams = {}
            if email is not None:
                update_params["email"] = email

            if name is not None:
                update_params["name"] = name

            if address is not None:
                update_params["address"] = _build_stripe_address(
                    address, "customer_update"
                )

            if validate_tax_location:
                update_params["tax"] = {"validate_location": "immediately"}
                update_params["expand"] = ["tax"]

            customer = await self.stripe.customers.update_async(
                customer_id,
                params=update_params,
            )
            return customer
        except Exception as e:
            logger.exception(f"Error updating customer {customer_id}: {str(e)}")
            if validate_tax_location:
                raise
            return None

    async def create_tax_calculation(
        self,
        *,
        amount: int,
        currency: str,
        address: "BillingAddress",
        reference: str,
        tax_code: Optional[str] = None,
    ) -> stripe.tax.Calculation:
        line_item = CalculationService.CreateParamsLineItem(
            amount=amount,
            quantity=1,
            reference=reference,
            tax_behavior=settings.BILLING_TAX_BEHAVIOR,
        )
        if tax_code:
            line_item["tax_code"] = tax_code

        return await self.stripe.tax.calculations.create_async(
            params={
                "currency": currency,
                "customer_details": {
                    "address": _build_stripe_address(address, "tax_calculation"),
                    "address_source": "billing",
                },
                "line_items": [
                    line_item,
                ],
            }
        )

    async def commit_tax_transaction(
        self,
        *,
        calculation_id: str,
        reference: str,
    ) -> Optional[stripe.tax.Transaction]:
        """Commit a Stripe Tax Calculation as a Tax Transaction.

        Required for tax to appear in the Stripe Tax dashboard for
        standalone PaymentIntents — unlike subscriptions (which use
        `automatic_tax`), PIs do not auto-commit their calculation.

        `reference` should be a stable, unique identifier (the
        PaymentIntent id is the natural choice). Stripe rejects re-use of
        the same reference; we swallow that error so webhook retries are
        safe.
        """
        try:
            logger.info(
                f"Committing Stripe tax transaction: calculation={calculation_id} "
                f"reference={reference}"
            )
            transaction = (
                await self.stripe.tax.transactions.create_from_calculation_async(
                    params={
                        "calculation": calculation_id,
                        "reference": reference,
                    },
                )
            )
            logger.info(
                f"Committed Stripe tax transaction {getattr(transaction, 'id', '?')} "
                f"for {reference}"
            )
            return transaction
        except stripe.StripeError as e:
            logger.warning(
                f"Failed to commit Stripe tax transaction for calculation "
                f"{calculation_id} (reference {reference}): {str(e)}"
            )
            return None

    async def update_subscription_metadata(
        self, subscription_id: str, metadata: Dict[str, str]
    ) -> Optional[stripe.Subscription]:
        """
        Update metadata for a Stripe subscription.

        Args:
            subscription_id: The Stripe subscription ID to update
            metadata: Metadata to update or add

        Returns:
            Updated Stripe subscription object or None if update failed
        """
        try:
            subscription = await self.stripe.subscriptions.update_async(
                subscription_id,
                params={"metadata": metadata},
            )
            return subscription
        except Exception as e:
            logger.exception(
                f"Error updating subscription metadata {subscription_id}: {str(e)}"
            )
            return None

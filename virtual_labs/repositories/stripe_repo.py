from typing import Dict, List, Optional, cast
from uuid import UUID

import stripe
from loguru import logger
from stripe import Customer, CustomerService, SignatureVerificationError

from virtual_labs.infrastructure.settings import settings
from virtual_labs.infrastructure.stripe.config import stripe_client


class StripeRepository:
    def __init__(self) -> None:
        """
        initialize the Stripe service
        """

        self.api_key = settings.STRIPE_SECRET_KEY
        self.webhook_secret = settings.STRIPE_WEBHOOK_SECRET
        self.stripe = stripe_client
        stripe.api_key = settings.STRIPE_SECRET_KEY

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
                    "expand": ["latest_invoice.payment_intent"],
                    "collection_method": "charge_automatically",  # NOTE: this is to charge the user at creation time
                    "metadata": metadata or {},
                    "payment_settings": {
                        "save_default_payment_method": "on_subscription"
                    },
                    # "discounts": [
                    #     {
                    #         "coupon": discount_id,
                    #     }
                    # ]
                    # if discount_id
                    # else "",
                    "description": "Creating subscription",
                }
            )
            return subscription
        except Exception as e:
            logger.exception(
                f"Error creating subscription for customer {customer_id}: {str(e)}"
            )
            raise

    async def cancel_subscription(
        self, subscription_id: str, cancel_immediately: bool = False
    ) -> Optional[stripe.Subscription]:
        """
        cancel a subscription in Stripe.

        Args:
            subscription_id: stripe subscription id
            cancel_immediately: Whether to cancel immediately or at period end

        Returns:
            The updated subscription
        """
        try:
            if cancel_immediately:
                subscription = await self.stripe.subscriptions.cancel_async(
                    subscription_id
                )
            else:
                subscription = await self.stripe.subscriptions.update_async(
                    subscription_id, params={"cancel_at_period_end": True}
                )

            return subscription
        except Exception as e:
            logger.exception(
                f"Error canceling subscription {subscription_id}: {str(e)}"
            )
            raise

    async def create_customer(
        self,
        user_id: UUID,
        email: str,
        name: Optional[str] = None,
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

            customer = await self.stripe.customers.create_async(customer_data)
            return customer
        except stripe.StripeError as e:
            logger.error(f"Failed to create Stripe customer: {str(e)}")
            return None

    async def create_payment_intent(
        self,
        amount: int,
        currency: str,
        customer_id: str,
        virtual_lab_id: UUID,
        payment_method_id: str,
        metadata: Optional[Dict[str, str]] = None,
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
            payment_intent = await self.stripe.payment_intents.create_async(
                params={
                    "amount": amount,
                    "currency": currency,
                    "customer": customer_id,
                    "payment_method": payment_method_id,
                    "metadata": metadata or {},
                    "confirm": True,
                    "description": "Adding credit",
                    "return_url": f"{settings.DEPLOYMENT_NAMESPACE}/app/virtual-lab/lab/{str(virtual_lab_id)}/admin?panel=purchases",
                },
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

            customer = await self.stripe.customers.update_async(
                customer_id,
                params=update_params,
            )
            return customer
        except Exception as e:
            logger.exception(f"Error updating customer {customer_id}: {str(e)}")
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
                subscription_id, params={"metadata": metadata}
            )
            return subscription
        except Exception as e:
            logger.exception(
                f"Error updating subscription metadata {subscription_id}: {str(e)}"
            )
            return None

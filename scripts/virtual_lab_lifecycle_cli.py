#!/usr/bin/env python
import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
import stripe
from pydantic import UUID4, EmailStr

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from virtual_labs.domain.invite import AddUser
from virtual_labs.domain.labs import VirtualLabCreate
from virtual_labs.domain.subscription import CreateSubscriptionRequest
from virtual_labs.infrastructure.db.models import (
    PaymentStatus,
    Subscription,
    SubscriptionPayment,
    SubscriptionStatus,
    VirtualLab,
)
from virtual_labs.infrastructure.settings import settings
from virtual_labs.infrastructure.stripe.config import stripe_client
from virtual_labs.infrastructure.stripe.webhook import StripeWebhook
from virtual_labs.core.types import UserRoleEnum

# Mock authentication token for API calls
MOCK_AUTH_TOKEN = "mock_auth_token"

# CLI command handlers
async def create_virtual_lab(args):
    """Create a new virtual lab"""
    print(f"Creating virtual lab: {args.name}")
    
    # Prepare the virtual lab creation payload
    lab_create = VirtualLabCreate(
        name=args.name,
        description=args.description or f"Description for {args.name}",
        reference_email=args.email,
        entity=args.entity or "Company",
        plan_id=args.plan_id,
        include_members=[
            AddUser(email=args.email, role=UserRoleEnum.admin)
        ] if args.include_self else None
    )
    
    # Make API call to create the virtual lab
    async with httpx.AsyncClient(base_url=args.api_url) as client:
        response = await client.post(
            "/virtual-labs",
            json=lab_create.model_dump(),
            headers={"Authorization": f"Bearer {MOCK_AUTH_TOKEN}"}
        )
        
        if response.status_code == 200:
            result = response.json()
            virtual_lab_id = result["data"]["virtual_lab"]["id"]
            print(f"Virtual lab created successfully with ID: {virtual_lab_id}")
            print(json.dumps(result, indent=2))
            return virtual_lab_id
        else:
            print(f"Failed to create virtual lab: {response.status_code}")
            print(response.text)
            return None

async def create_subscription(args):
    """Create a subscription for a virtual lab"""
    print(f"Creating subscription for virtual lab: {args.virtual_lab_id}")
    
    # First, we need to create a payment method
    payment_method = await create_payment_method(args)
    if not payment_method:
        print("Failed to create payment method")
        return None
    
    # Get available subscription plans
    async with httpx.AsyncClient(base_url=args.api_url) as client:
        plans_response = await client.get(
            "/subscriptions/plans",
            headers={"Authorization": f"Bearer {MOCK_AUTH_TOKEN}"}
        )
        
        if plans_response.status_code != 200:
            print(f"Failed to get subscription plans: {plans_response.status_code}")
            print(plans_response.text)
            return None
        
        plans = plans_response.json()
        
        # Find the appropriate price ID based on the interval (monthly/yearly)
        price_id = None
        for plan in plans:
            for price in plan["prices"]:
                if price["interval"] == args.interval:
                    price_id = price["id"]
                    break
            if price_id:
                break
        
        if not price_id:
            print(f"No price found for interval: {args.interval}")
            return None
        
        # Create the subscription
        subscription_request = CreateSubscriptionRequest(
            virtual_lab_id=args.virtual_lab_id,
            price_id=price_id,
            payment_method_id=payment_method["id"],
            metadata={"test": "true"}
        )
        
        response = await client.post(
            "/subscriptions",
            json=subscription_request.model_dump(),
            headers={"Authorization": f"Bearer {MOCK_AUTH_TOKEN}"}
        )
        
        if response.status_code == 200:
            result = response.json()
            subscription_id = result["subscription"]["id"]
            print(f"Subscription created successfully with ID: {subscription_id}")
            print(json.dumps(result, indent=2))
            return subscription_id
        else:
            print(f"Failed to create subscription: {response.status_code}")
            print(response.text)
            return None

async def create_payment_method(args):
    """Create a test payment method in Stripe"""
    try:
        payment_method = await stripe_client.payment_methods.create_async(
            type="card",
            card={
                "number": "4242424242424242",  # Test card number
                "exp_month": 12,
                "exp_year": datetime.now().year + 1,
                "cvc": "123",
            },
            billing_details={
                "name": "Test User",
                "email": args.email,
            },
        )
        
        print(f"Created payment method: {payment_method.id}")
        return payment_method
    except Exception as e:
        print(f"Error creating payment method: {str(e)}")
        return None

async def make_payment(args):
    """Make a payment for a subscription"""
    print(f"Making payment for subscription: {args.subscription_id}")
    
    # In a real scenario, this would involve creating a payment intent
    # and confirming it, but for our CLI we'll simulate this by
    # directly creating a payment record
    
    try:
        # Get the subscription
        async with httpx.AsyncClient(base_url=args.api_url) as client:
            response = await client.get(
                f"/subscriptions/{args.subscription_id}",
                headers={"Authorization": f"Bearer {MOCK_AUTH_TOKEN}"}
            )
            
            if response.status_code != 200:
                print(f"Failed to get subscription: {response.status_code}")
                print(response.text)
                return None
            
            subscription_data = response.json()
            
        # Create a payment intent in Stripe
        payment_intent = await stripe_client.payment_intents.create_async(
            amount=subscription_data["amount"],
            currency=subscription_data["currency"],
            payment_method_types=["card"],
            metadata={
                "subscription_id": args.subscription_id,
                "virtual_lab_id": args.virtual_lab_id,
                "test": "true"
            }
        )
        
        # Confirm the payment intent
        confirmed_intent = await stripe_client.payment_intents.confirm_async(
            payment_intent.id,
            payment_method="pm_card_visa"  # Test payment method
        )
        
        print(f"Payment created with intent ID: {payment_intent.id}")
        print(json.dumps(payment_intent, indent=2, default=str))
        
        return payment_intent.id
    except Exception as e:
        print(f"Error making payment: {str(e)}")
        return None

async def advance_subscription(args):
    """Advance a subscription to simulate time passing"""
    print(f"Advancing subscription: {args.subscription_id}")
    
    try:
        # Get the subscription from the database
        # This would normally be done through the API, but for simulation
        # we'll use the Stripe API directly
        
        # First, get our subscription from the API to get the Stripe subscription ID
        async with httpx.AsyncClient(base_url=args.api_url) as client:
            response = await client.get(
                f"/subscriptions/{args.subscription_id}",
                headers={"Authorization": f"Bearer {MOCK_AUTH_TOKEN}"}
            )
            
            if response.status_code != 200:
                print(f"Failed to get subscription: {response.status_code}")
                print(response.text)
                return None
            
            subscription_data = response.json()
            stripe_subscription_id = subscription_data["stripe_subscription_id"]
        
        # Now use the Stripe API to simulate advancing the subscription
        # This creates an invoice and attempts to pay it
        invoice = await stripe_client.invoices.create_async(
            customer=subscription_data["customer_id"],
            subscription=stripe_subscription_id,
            auto_advance=True,
        )
        
        # Finalize and pay the invoice
        finalized = await stripe_client.invoices.finalize_invoice_async(invoice.id)
        paid = await stripe_client.invoices.pay_async(invoice.id)
        
        print(f"Advanced subscription with new invoice: {invoice.id}")
        print(f"Invoice status: {paid.status}")
        
        # Simulate webhook event for testing
        if args.test_webhook:
            await simulate_webhook_event(
                "invoice.payment_succeeded", 
                {"id": invoice.id}
            )
        
        return invoice.id
    except Exception as e:
        print(f"Error advancing subscription: {str(e)}")
        return None

async def simulate_webhook_event(event_type, object_data):
    """Simulate a Stripe webhook event"""
    print(f"Simulating webhook event: {event_type}")
    
    # Create a mock event
    event_data = {
        "id": f"evt_{uuid.uuid4().hex}",
        "object": "event",
        "api_version": "2020-08-27",
        "created": int(datetime.now().timestamp()),
        "data": {
            "object": object_data
        },
        "livemode": False,
        "pending_webhooks": 0,
        "request": {
            "id": None,
            "idempotency_key": None
        },
        "type": event_type
    }
    
    # Send to webhook endpoint
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.API_URL}/payments/webhook",
            json=event_data,
            headers={
                "Stripe-Signature": "mock_signature",
                "Content-Type": "application/json"
            }
        )
        
        print(f"Webhook response: {response.status_code}")
        print(response.text)
        
        return response.status_code == 200

async def make_standalone_payment(args):
    """Make a standalone payment not tied to a subscription"""
    print(f"Making standalone payment for virtual lab: {args.virtual_lab_id}")
    
    try:
        # Create a payment intent in Stripe
        payment_intent = await stripe_client.payment_intents.create_async(
            amount=args.amount,
            currency="usd",
            payment_method_types=["card"],
            metadata={
                "virtual_lab_id": args.virtual_lab_id,
                "topup_balance": "true",
                "test": "true"
            }
        )
        
        # Confirm the payment intent
        confirmed_intent = await stripe_client.payment_intents.confirm_async(
            payment_intent.id,
            payment_method="pm_card_visa"  # Test payment method
        )
        
        print(f"Standalone payment created with intent ID: {payment_intent.id}")
        print(json.dumps(payment_intent, indent=2, default=str))
        
        # Simulate webhook event for testing
        if args.test_webhook:
            await simulate_webhook_event(
                "charge.succeeded", 
                {
                    "id": f"ch_{uuid.uuid4().hex}",
                    "payment_intent": payment_intent.id,
                    "amount": args.amount,
                    "currency": "usd",
                    "metadata": {
                        "virtual_lab_id": args.virtual_lab_id,
                        "topup_balance": "true"
                    }
                }
            )
        
        return payment_intent.id
    except Exception as e:
        print(f"Error making standalone payment: {str(e)}")
        return None

def main():
    parser = argparse.ArgumentParser(description="Virtual Lab Lifecycle CLI")
    parser.add_argument("--api-url", default="http://localhost:8000", help="API base URL")
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Create Virtual Lab command
    create_lab_parser = subparsers.add_parser("create-lab", help="Create a new virtual lab")
    create_lab_parser.add_argument("--name", required=True, help="Virtual lab name")
    create_lab_parser.add_argument("--description", help="Virtual lab description")
    create_lab_parser.add_argument("--email", required=True, help="Reference email")
    create_lab_parser.add_argument("--entity", default="Company", help="Entity name")
    create_lab_parser.add_argument("--plan-id", type=int, default=1, help="Plan ID")
    create_lab_parser.add_argument("--include-self", action="store_true", help="Include self as member")
    
    # Create Subscription command
    create_sub_parser = subparsers.add_parser("create-subscription", help="Create a subscription")
    create_sub_parser.add_argument("--virtual-lab-id", required=True, help="Virtual lab ID")
    create_sub_parser.add_argument("--email", required=True, help="Email for payment method")
    create_sub_parser.add_argument("--interval", choices=["month", "year"], default="month", help="Billing interval")
    
    # Make Payment command
    payment_parser = subparsers.add_parser("make-payment", help="Make a payment for a subscription")
    payment_parser.add_argument("--subscription-id", required=True, help="Subscription ID")
    payment_parser.add_argument("--virtual-lab-id", required=True, help="Virtual lab ID")
    
    # Advance Subscription command
    advance_parser = subparsers.add_parser("advance-subscription", help="Advance a subscription")
    advance_parser.add_argument("--subscription-id", required=True, help="Subscription ID")
    advance_parser.add_argument("--test-webhook", action="store_true", help="Test webhook after advancing")
    
    # Standalone Payment command
    standalone_parser = subparsers.add_parser("standalone-payment", help="Make a standalone payment")
    standalone_parser.add_argument("--virtual-lab-id", required=True, help="Virtual lab ID")
    standalone_parser.add_argument("--amount", type=int, default=5000, help="Amount in cents")
    standalone_parser.add_argument("--test-webhook", action="store_true", help="Test webhook after payment")
    
    # Parse arguments
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Execute the appropriate command
    loop = asyncio.get_event_loop()
    if args.command == "create-lab":
        loop.run_until_complete(create_virtual_lab(args))
    elif args.command == "create-subscription":
        loop.run_until_complete(create_subscription(args))
    elif args.command == "make-payment":
        loop.run_until_complete(make_payment(args))
    elif args.command == "advance-subscription":
        loop.run_until_complete(advance_subscription(args))
    elif args.command == "standalone-payment":
        loop.run_until_complete(make_standalone_payment(args))

if __name__ == "__main__":
    main()

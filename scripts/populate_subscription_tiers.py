#!/usr/bin/env python3
"""
Script to populate subscription plan data in the database.
This script creates the Free, Pro, and Premium plans with appropriate pricing options.

Usage:
    poetry run populate-tiers [--test]

Environment variables:
    DATABASE_URL: Database connection string (defaults to postgresql+asyncpg://postgres:postgres@localhost:15432/vlm)
    STRIPE_API_KEY: Stripe API key for fetching plan details (optional)
    PROD_ID: stripe product id for the plan
    SANITY_ID: sanity id for the plan
"""

import asyncio
import json
import os
import stripe
import argparse
from typing import Dict
from uuid import UUID, uuid4

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from virtual_labs.infrastructure.db.models import SubscriptionTier
load_dotenv(".env.local")

# Default database URL if not set in environment
DEFAULT_DATABASE_URL = "postgresql+asyncpg://vlm:vlm@localhost:15432/vlm"
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)

# Default values for Stripe and Sanity IDs
DEFAULT_PROD_ID = "prod_test_example123"
DEFAULT_FREE_SANITY_ID = "831faa5c-dbbd-4d9a-9b1a-1cd661b61e40"
DEFAULT_PRO_SANITY_ID = "21bfee77-bcaf-4c93-9447-14ffa1343a31"
DEFAULT_PREMIUM_SANITY_ID = "78bd43f5-ad04-4d76-8374-23b35ff6dc6a"

STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
PROD_ID = os.getenv("PROD_ID", DEFAULT_PROD_ID)
FREE_SANITY_ID = os.getenv("FREE_SANITY_ID", DEFAULT_FREE_SANITY_ID)
PRO_SANITY_ID = os.getenv("PRO_SANITY_ID", DEFAULT_PRO_SANITY_ID)
PREMIUM_SANITY_ID = os.getenv("PREMIUM_SANITY_ID", DEFAULT_PREMIUM_SANITY_ID)


# Fixed UUIDs for test mode
TEST_FREE_TIER_ID = UUID("00000000-0000-0000-0000-000000000001")
TEST_PRO_TIER_ID = UUID("00000000-0000-0000-0000-000000000002")
TEST_PREMIUM_TIER_ID = UUID("00000000-0000-0000-0000-000000000003")

FREE_PLAN = {
    "stripe_product_id": None,
    "name": "Free",
    "description": "Free plan",
    "active": True,
    "sanity_id": FREE_SANITY_ID,
    "stripe_monthly_price_id": None,
    "monthly_amount": 0,
    "monthly_discount": 0,
    "yearly_discount": 0,
    "stripe_yearly_price_id": None,
    "yearly_amount": 0,
    "features": None,
    "currency": "chf",
    "tier": "free",
    "monthly_credits": 100,
    "yearly_credits": 100,
    "plan_metadata": {
        "tier": "free",
    }
}

PRO_PLAN = {
    "stripe_product_id": PROD_ID,
    "name": "Pro",
    "description": "Pro plan with advanced features",
    "active": True,
    "sanity_id": PRO_SANITY_ID,
    "stripe_monthly_price_id": "price_ProMonthlyExample123", 
    "monthly_amount": 5000, 
    "monthly_discount": 2500,
    "yearly_discount": 27500,
    "stripe_yearly_price_id": "price_ProYearlyExample456",
    "yearly_amount": 55000, 
    "features": None,
    "currency": "chf",
    "tier": "pro",
    "monthly_credits": 50,
    "yearly_credits": 650,
    "plan_metadata": {
        "tier": "pro",
    }
}

PREMIUM_PLAN = {
    "stripe_product_id": None,
    "name": "Premium",
    "description": "Premium plan with tailored requirements",
    "active": True,
    "sanity_id": PREMIUM_SANITY_ID, 
    "stripe_monthly_price_id": None,
    "monthly_amount": 0,
    "monthly_discount": 0,
    "yearly_discount": 0,
    "stripe_yearly_price_id":None,
    "yearly_amount": 0, 
    "features": None,
    "currency": "chf",
    "tier": "premium",
    "monthly_credits": 0,
    "yearly_credits": 0,
    "plan_metadata": {
        "tier": "premium",
    }
}

PLANS = [FREE_PLAN, PRO_PLAN, PREMIUM_PLAN]

async def fetch_stripe_data_for_plan(plan_name: str, test_mode: bool = False) -> Dict:
    if test_mode:
        if plan_name.lower() == "free":
            return FREE_PLAN
        elif plan_name.lower() == "pro":
            return PRO_PLAN
        elif plan_name.lower() == "premium":
            return PREMIUM_PLAN
        else:
            raise ValueError(f"Unknown plan name: {plan_name}")

    if plan_name.lower() == "free":
        return FREE_PLAN
    if plan_name.lower() == "premium":
        return PREMIUM_PLAN

    try:
        stripe_client = stripe.StripeClient(
            api_key=STRIPE_API_KEY,
        )

        product = await stripe_client.products.retrieve_async(PROD_ID)
        prices = await stripe_client.prices.list_async(
            params={
                "product": PROD_ID
            }
        )

        monthly_price =  next((p for p in prices.data if p.recurring.interval == "month"), None)
        yearly_price = next((p for p in prices.data if p.recurring.interval == "year"), None)

        if not monthly_price or not yearly_price:
            logger.warning(f"Missing prices for {plan_name} plan, using predefined data")
            if plan_name.lower() == "pro":
                return PRO_PLAN
            else:
                raise ValueError(f"Unknown plan name: {plan_name}")
            

        plan_data = {
            "stripe_product_id": PROD_ID,
            "name": product.name,
            "description": product.description or f"{product.name} plan",
            "active": product.active,
            "sanity_id": PRO_SANITY_ID,
            "stripe_monthly_price_id": monthly_price.id,
            "monthly_amount": monthly_price.unit_amount,
            "monthly_discount": monthly_price.unit_amount /2,
            "stripe_yearly_price_id": yearly_price.id,
            "yearly_amount": yearly_price.unit_amount,
            "yearly_discount": yearly_price.unit_amount /2,
            "currency": monthly_price.currency,
            "tier": "pro",
            "monthly_credits": 50,
            "yearly_credits": 650,
            "features": json.loads(product.metadata.get("features", '{}')),
            "plan_metadata":{
                "tier": "pro",
            }
        }
        return plan_data
    except Exception as e:
        logger.exception(f"Error fetching Stripe data for {plan_name}: {str(e)}")
        if plan_name.lower() == "pro":
            return PRO_PLAN
        else:
            raise ValueError(f"Unknown plan name: {plan_name}")


async def populate_subscription_tiers(test_mode: bool = False):
    if not DATABASE_URL:
        logger.error("DATABASE_URL environment variable is not set")
        return

    engine = create_async_engine(DATABASE_URL, echo=True)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with async_session() as session:
            for t_plan in PLANS:
                plan_name = t_plan["name"]
                
                plan_data = await fetch_stripe_data_for_plan(plan_name, test_mode)

                existing_plan = None
                try:
                    if plan_data["stripe_product_id"]:
                        result = await session.execute(
                            f"SELECT id FROM subscription_tier WHERE stripe_product_id = '{plan_data['stripe_product_id']}'"
                        )
                    else:
                        result = await session.execute(
                            f"SELECT id FROM subscription_tier WHERE name = '{plan_data['name']}'"
                        )
                    existing_plan = result.scalar_one_or_none()
                except Exception as e:
                    logger.warning(f"Error checking for existing plan {plan_name}: {str(e)}")
                    
                if existing_plan:
                    logger.info(f"Plan {plan_name} already exists")
                    continue

                # Use fixed UUIDs in test mode
                tier_id = None
                if test_mode:
                    if plan_name.lower() == "free":
                        tier_id = TEST_FREE_TIER_ID
                    elif plan_name.lower() == "pro":
                        tier_id = TEST_PRO_TIER_ID
                    elif plan_name.lower() == "premium":
                        tier_id = TEST_PREMIUM_TIER_ID
                else:
                    if plan_name.lower() == "free":
                        tier_id = UUID("edb05acd-f29a-4d84-a53a-d6ca398143a4")
                    elif plan_name.lower() == "pro":
                        tier_id = UUID("e8abe72f-1763-4572-9050-642c7122d155")
                    elif plan_name.lower() == "premium":
                        tier_id = UUID("cf4b96d7-df0e-4617-a4e1-09fd2b4a62f1")

                tier = SubscriptionTier(
                    id=tier_id,
                    stripe_product_id=plan_data["stripe_product_id"],
                    name=plan_data["name"],
                    description=plan_data["description"],
                    active=plan_data["active"],
                    sanity_id=plan_data["sanity_id"],
                    stripe_monthly_price_id=plan_data["stripe_monthly_price_id"],
                    monthly_amount=plan_data["monthly_amount"],
                    monthly_discount=plan_data["monthly_discount"],
                    yearly_discount=plan_data["yearly_discount"],
                    stripe_yearly_price_id=plan_data["stripe_yearly_price_id"],
                    yearly_amount=plan_data["yearly_amount"],
                    currency=plan_data["currency"],
                    features=plan_data["features"],
                    tier=plan_data["tier"],
                    monthly_credits= plan_data["monthly_credits"],
                    yearly_credits= plan_data["yearly_credits"],
                    plan_metadata=plan_data["plan_metadata"]
                )
                
                # Create a clean dictionary of values
                values_dict = {
                    k: v for k, v in tier.__dict__.items() 
                    if not k.startswith('_')
                }
                
                # Generate a raw SQL query instead of using SQLAlchemy's compile
                columns = []
                placeholders = []
                values = []
                
                for key, value in values_dict.items():
                    columns.append(key)
                    placeholders.append("%s")
                    
                    # Handle JSON fields
                    if key in ['features', 'plan_metadata'] and value is not None:
                        values.append(json.dumps(value))
                    else:
                        values.append(value)
                
                columns_str = ", ".join(columns)
                placeholders_str = ", ".join(placeholders)
                
                # format values for display
                display_values = []
                for val in values:
                    if val is None:
                        display_values.append("NULL")
                    elif isinstance(val, str):
                        # Escape single quotes in strings
                        escaped_val = val.replace("'", "''")
                        display_values.append(f"'{escaped_val}'")
                    elif isinstance(val, bool):
                        display_values.append(str(val).lower())
                    else:
                        display_values.append(str(val))
                

                sql_query = f"""
                    -- SQL Query for {plan_name} plan
                    INSERT INTO subscription_tier (
                        {',\n    '.join(columns)}
                    ) VALUES (
                        {',\n    '.join(display_values)}
                    );
                    """
                print(sql_query)
                

                session.add(tier)
                await session.commit()
                await session.refresh(tier)
                
                logger.success(f"Added {tier.name} plan")

            logger.success("Successfully populated all subscription plans")

    except Exception as e:
        logger.exception(f"Error populating subscription plans: {str(e)}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Populate subscription tiers')
    parser.add_argument('--test', action='store_true', help='Run in test mode without Stripe API calls')
    args = parser.parse_args()

    logger.info(f"Starting subscription plan population via Poetry (test mode: {args.test})")
    asyncio.run(populate_subscription_tiers(test_mode=args.test))
    logger.info("Subscription plan population completed")

def run_async():
    """
    entrypoint for poetry script command.
    """
    parser = argparse.ArgumentParser(description='Populate subscription tiers')
    parser.add_argument('--test', action='store_true', help='Run in test mode without Stripe API calls')
    args = parser.parse_args()

    logger.info(f"Starting subscription plan population via Poetry (test mode: {args.test})")
    asyncio.run(populate_subscription_tiers(test_mode=args.test))
    logger.info("Subscription plan population completed")
    return 0
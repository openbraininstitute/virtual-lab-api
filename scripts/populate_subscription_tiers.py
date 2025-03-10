#!/usr/bin/env python3
"""
Script to populate subscription plan data in the database.
This script creates the Free, Pro, and Premium plans with appropriate pricing options.

Usage:

Environment variables:
    DATABASE_URL: Database connection string
    STRIPE_API_KEY: Stripe API key for fetching plan details (optional)
    PROD_ID: stripe product id for the plan
    SANITY_ID: sanity id for the plan
"""

import asyncio
import json
import os
import stripe
from typing import Dict

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from virtual_labs.infrastructure.db.models import SubscriptionTier
load_dotenv(".env.local")

DATABASE_URL = os.getenv("DATABASE_URL")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
PROD_ID = os.getenv("PROD_ID")
FREE_SANITY_ID = os.getenv("FREE_SANITY_ID")
PRO_SANITY_ID = os.getenv("PRO_SANITY_ID")
PREMIUM_SANITY_ID = os.getenv("PREMIUM_SANITY_ID")

stripe_client = stripe.StripeClient(
    api_key=STRIPE_API_KEY,
)


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
    "plan_metadata": {
        "tier": "premium",
    }
}

PLANS = [FREE_PLAN, PRO_PLAN, PREMIUM_PLAN]

async def fetch_stripe_data_for_plan(plan_name: str) -> Dict:
    if plan_name.lower() == "free":
        return FREE_PLAN
    if plan_name.lower() == "premium":
        return PREMIUM_PLAN

    try:

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


async def populate_subscription_tiers():
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
                
                plan_data = await fetch_stripe_data_for_plan(plan_name)

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
                    

                tier = SubscriptionTier(
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
    asyncio.run(populate_subscription_tiers()) 

def run_async():
    """
    entrypoint for poetry script command.
    """

    logger.info("Starting subscription plan population via Poetry")
    asyncio.run(populate_subscription_tiers())
    logger.info("Subscription plan population completed")
    return 0 
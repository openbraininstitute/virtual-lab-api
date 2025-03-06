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
from typing import Dict

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from virtual_labs.infrastructure.db.models import SubscriptionPlan
from virtual_labs.infrastructure.stripe.config import stripe_client as stripe

load_dotenv(".env.local")

DATABASE_URL = os.getenv("DATABASE_URL")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
PROD_ID = os.getenv("PROD_ID")
FREE_SANITY_ID = os.getenv("FREE_SANITY_ID")
PRO_SANITY_ID = os.getenv("PRO_SANITY_ID")
PREMIUM_SANITY_ID = os.getenv("PREMIUM_SANITY_ID")


FREE_PLAN = {
    "stripe_product_id": None,
    "name": "Free",
    "description": "Free tier with free features",
    "active": True,
    "sanity_id": FREE_SANITY_ID,
    "stripe_monthly_price_id": None,
    "monthly_amount": 0,
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
    "description": "Professional plan with advanced features",
    "active": True,
    "sanity_id": PRO_SANITY_ID,
    "stripe_monthly_price_id": "price_ProMonthlyExample123", 
    "monthly_amount": 50, 
    "stripe_yearly_price_id": "price_ProYearlyExample456",
    "yearly_amount": 550, 
    "features": None,
    "currency": "chf",
    "plan_metadata": {
        "tier": "pro",
    }
}

PREMIUM_PLAN = {
    "stripe_product_id": None,
    "name": "Premium",
    "description": "Enterprise grade plan with maximum features",
    "active": True,
    "sanity_id": PREMIUM_SANITY_ID, 
    "stripe_monthly_price_id": None,
    "monthly_amount": 0,
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
        
        product = await stripe.products.retrieve_async(PROD_ID)
        prices = await stripe.prices.list_async(
            params={
                "product": PROD_ID
            }
        )

        print("ᦨ #  populate_subscription_plans.py:107 #  prices:", prices);

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
            "stripe_yearly_price_id": yearly_price.id,
            "yearly_amount": yearly_price.unit_amount,
            "currency": monthly_price.currency,
            "features": json.loads(product.metadata.get("features", '{}')),
            "plan_metadata": product.metadata
        }
        return plan_data
    except Exception as e:
        logger.exception(f"Error fetching Stripe data for {plan_name}: {str(e)}")
        if plan_name.lower() == "pro":
            return PRO_PLAN
        else:
            raise ValueError(f"Unknown plan name: {plan_name}")


async def populate_subscription_plans():
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
                            f"SELECT id FROM subscription_plan WHERE stripe_product_id = '{plan_data['stripe_product_id']}'"
                        )
                    else:
                        result = await session.execute(
                            f"SELECT id FROM subscription_plan WHERE name = '{plan_data['name']}'"
                        )
                    existing_plan = result.scalar_one_or_none()
                except Exception as e:
                    logger.warning(f"Error checking for existing plan {plan_name}: {str(e)}")
                    
                if existing_plan:
                    logger.info(f"Plan {plan_name} already exists")
                    continue
                    

                plan = SubscriptionPlan(
                    stripe_product_id=plan_data["stripe_product_id"],
                    name=plan_data["name"],
                    description=plan_data["description"],
                    active=plan_data["active"],
                    sanity_id=plan_data["sanity_id"],
                    stripe_monthly_price_id=plan_data["stripe_monthly_price_id"],
                    monthly_amount=plan_data["monthly_amount"],
                    stripe_yearly_price_id=plan_data["stripe_yearly_price_id"],
                    yearly_amount=plan_data["yearly_amount"],
                    currency=plan_data["currency"],
                    features=plan_data["features"],
                    plan_metadata=plan_data["plan_metadata"]
                )
                
                session.add(plan)
                await session.commit()
                await session.refresh(plan)
                
                logger.success(f"Added {plan.name} plan")

            logger.success("Successfully populated all subscription plans")

    except Exception as e:
        logger.exception(f"Error populating subscription plans: {str(e)}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(populate_subscription_plans()) 

def run_async():
    """
    entrypoint for poetry script command.
    """

    logger.info("Starting subscription plan population via Poetry")
    asyncio.run(populate_subscription_plans())
    logger.info("Subscription plan population completed")
    return 0 
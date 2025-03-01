import stripe

from virtual_labs.infrastructure.settings import settings

# Initialize the async Stripe client
stripe_client = stripe.StripeClient(
    api_key=settings.STRIPE_SECRET_KEY,
)

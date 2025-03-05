import stripe

from virtual_labs.infrastructure.settings import settings

stripe_client = stripe.StripeClient(
    api_key=settings.STRIPE_SECRET_KEY,
)

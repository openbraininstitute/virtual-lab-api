import stripe

from virtual_labs.infrastructure.settings import settings

stripe.api_key = settings.STRIPE_SECRET_KEY

stripe_client = stripe.StripeClient(
    settings.STRIPE_SECRET_KEY,
)

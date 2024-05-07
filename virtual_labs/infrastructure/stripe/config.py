import stripe

from virtual_labs.infrastructure.settings import settings

stripe_client = stripe.StripeClient(
    settings.STRIPE_SECRET_KEY,
)


test_stripe_client = stripe.StripeClient(
    settings.TEST_STRIPE_SECRET_KEY,
)

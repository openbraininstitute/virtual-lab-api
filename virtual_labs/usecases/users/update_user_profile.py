from http import HTTPStatus
from typing import Any, Dict, Tuple, cast

from fastapi import Response
from keycloak import KeycloakError, KeycloakPutError  # type: ignore[import-untyped]
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from virtual_labs.core.exceptions.api_error import VliError, VliErrorCode
from virtual_labs.core.exceptions.generic_exceptions import (
    EntityNotCreated,
    EntityNotFound,
)
from virtual_labs.core.response.api_response import VliResponse
from virtual_labs.domain.user import (
    Address,
    UpdateUserProfileRequest,
    UserProfile,
    UserProfileResponse,
)
from virtual_labs.infrastructure.kc.models import AuthUser
from virtual_labs.infrastructure.stripe import get_stripe_repository
from virtual_labs.repositories.stripe_user_repo import (
    StripeUserMutationRepository,
    StripeUserQueryRepository,
)
from virtual_labs.repositories.user_repo import (
    UserMutationRepository,
    UserQueryRepository,
)
from virtual_labs.shared.utils.auth import get_user_id_from_auth


async def update_user_profile(
    payload: UpdateUserProfileRequest,
    auth: Tuple[AuthUser, str],
    session: AsyncSession,
) -> Response:
    """
    update the profile information for the authenticated user.

    Args:
        payload: The user profile data to update
        auth: auth tuple

    Returns:
        Response: updated user profile information
    """
    try:
        _, token = auth
        user_id = get_user_id_from_auth(auth)
        user_query_repo = UserQueryRepository()
        user_mutation_repo = UserMutationRepository()
        stripe_user_repo = StripeUserQueryRepository(db_session=session)
        stripe_service = get_stripe_repository()
        stripe_user_mutation_repo = StripeUserMutationRepository(db_session=session)

        kc_user = await user_query_repo.get_user(user_id=str(user_id))

        if not kc_user:
            raise EntityNotFound

        update_data: Dict[str, Any] = {}
        update_data["email"] = payload.email
        if payload.first_name is not None:
            update_data["firstName"] = payload.first_name
        if payload.last_name is not None:
            update_data["lastName"] = payload.last_name

        attributes = kc_user.get("attributes", {}) or {}
        merged_attributes = {
            k: v if isinstance(v, list) else [str(v)] for k, v in attributes.items()
        }

        merged_attributes["country"] = [payload.country]

        if payload.address is not None:
            address_fields = {
                "street": payload.address.street,
                "postal_code": payload.address.postal_code,
                "locality": payload.address.locality,
                "region": payload.address.region,
            }

            address_updates = {
                k: [v] for k, v in address_fields.items() if v is not None
            }
            merged_attributes.update(address_updates)

        update_data["attributes"] = merged_attributes

        if update_data:
            await user_mutation_repo.Kc.a_update_user(
                user_id=str(user_id),
                payload=update_data,
            )

            kc_user = cast(
                Dict[str, Any], await user_query_repo.get_user_info(token=token)
            )

        # Fetch user via admin API to get attributes (address fields)
        kc_admin_user = await user_query_repo.get_user(user_id=str(user_id))
        attributes = kc_admin_user.get("attributes", {}) if kc_admin_user else {}

        def _attr(key: str) -> str:
            val = attributes.get(key, "")
            if isinstance(val, list):
                return val[0] if val else ""
            return str(val) if val else ""

        customer = await stripe_user_repo.get_by_user_id(
            user_id=user_id,
        )

        if customer is None:
            stripe_customer = await stripe_service.create_customer(
                user_id=user_id,
                email=payload.email,
                name=f"{payload.first_name or kc_user.get('given_name')} {payload.last_name or kc_user.get('family_name')}",
            )
            if stripe_customer is None:
                raise EntityNotCreated("Stripe customer creation failed")

            await stripe_user_mutation_repo.create(
                user_id=user_id,
                stripe_customer_id=stripe_customer.id,
            )
        else:
            assert customer.stripe_customer_id, "Customer not found"
            stripe_customer = await stripe_service.update_customer(
                customer_id=customer.stripe_customer_id,
                name=f"{payload.first_name or kc_user.get('given_name')} {payload.last_name or kc_user.get('family_name')}",
                email=payload.email,
            )

        user_profile = UserProfile(
            id=user_id,
            preferred_username=kc_user["preferred_username"],
            email=kc_user["email"],
            first_name=kc_user.get("given_name") or "",
            last_name=kc_user.get("family_name") or "",
            email_verified=kc_user["email_verified"],
            address=Address(
                street=_attr("street"),
                postal_code=_attr("postal_code"),
                locality=_attr("locality"),
                region=_attr("region"),
                country=_attr("country"),
            ),
        )

        return VliResponse.new(
            message="User profile updated successfully",
            data=UserProfileResponse(profile=user_profile).model_dump(),
        )
    except EntityNotFound as e:
        logger.error(f"User not found: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.ENTITY_NOT_FOUND,
            http_status_code=HTTPStatus.NOT_FOUND,
            message="User not found",
        )
    except KeycloakPutError as e:
        logger.error(
            f"Keycloak put error: {e.error_message} | {e.response_code} | {e.response_body}"
        )
        message = "An error occurred while updating the user profile"
        if (
            isinstance(e.response_body, bytes)
            and b"User exists with same email" in e.response_body
        ) or (
            isinstance(e.response_body, str)
            and "User exists with same email" in e.response_body
        ):
            message = "This email address cannot be used. Try another one or sign in if you already have an account."

        raise VliError(
            error_code=VliErrorCode.DATA_CONFLICT,
            http_status_code=HTTPStatus.CONFLICT,
            message=message,
        ) from e
    except KeycloakError as e:
        logger.error(f"Keycloak error: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.ENTITY_UPDATE__ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message=str(e) or "An error occurred while updating the user profile",
        ) from e
    except Exception as e:
        logger.exception(f"Error updating user profile: {str(e)}")
        raise VliError(
            error_code=VliErrorCode.INTERNAL_SERVER_ERROR,
            http_status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            message="An error occurred while updating the user profile",
        )

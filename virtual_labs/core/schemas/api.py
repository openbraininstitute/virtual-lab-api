from pydantic import BaseModel

from virtual_labs.core.exceptions.api_error import VlmErrorCode


class ErrorResponse(BaseModel):
    """The format of an error response from the Vlm API."""

    error_code: VlmErrorCode
    message: str

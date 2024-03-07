from pydantic import BaseModel

from virtual_labs.core.exceptions.api_error import VliErrorCode


class ErrorResponse(BaseModel):
    """The format of an error response from the Vlm API."""

    error_code: VliErrorCode
    message: str

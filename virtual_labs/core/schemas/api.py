from typing import Any

from pydantic import BaseModel

from virtual_labs.core.exceptions.api_error import VliErrorCode


class ErrorResponse(BaseModel):
    """The format of an error response from the Vlm API."""

    error_code: VliErrorCode
    message: str
    details: str | None = None
    data: dict[str, Any] | None = None

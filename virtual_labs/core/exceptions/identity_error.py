from dataclasses import dataclass


@dataclass
class IdentityError(Exception):
    message: str
    detail: str | None

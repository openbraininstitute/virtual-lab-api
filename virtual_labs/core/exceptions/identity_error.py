from dataclasses import dataclass


@dataclass
class IdentityError(Exception):
    message: str
    detail: str | None


class UserMismatch(Exception):
    pass

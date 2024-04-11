from dataclasses import dataclass


@dataclass
class IdentityError(Exception):
    message: str
    detail: str | None

    def __str__(self) -> str:
        return f"{self.message}"


class UserMismatch(Exception):
    pass

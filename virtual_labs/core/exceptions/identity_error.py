from dataclasses import dataclass


@dataclass
class IdentityError(Exception):
    message: str
    detail: str | None

    def __str__(self) -> str:
        return f"{self.message}"


class UserMismatch(Exception):
    pass


class UserMatch(Exception):
    def __init__(
        self, message: str = "Request User is matching Destination user"
    ) -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message

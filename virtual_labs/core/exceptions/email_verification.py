from typing import Any


class EmailVerificationException(Exception):
    def __init__(
        self,
        message: str = "Email verification error",
        data: dict[str, Any] | None = None,
    ) -> None:
        self.message = message
        self.data = data
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}: {self.message} {self.data}"

    def to_dict(self) -> dict[str, Any]:
        """
        Return the data dictionary when the object is treated as a dictionary.
        """
        return {
            "message": self.message,
            "data": self.data,
        }

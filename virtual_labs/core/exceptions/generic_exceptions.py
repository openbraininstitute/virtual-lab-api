from typing import Any, Dict


class UserNotInList(Exception):
    def __init__(self, message: str = "User not in list") -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class BudgetExceedLimit(Exception):
    def __init__(self, message: str = "Budget limit exceeded") -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class ProjectAlreadyDeleted(Exception):
    def __init__(self, message: str = "Project has already been deleted") -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class EntityAlreadyExists(Exception):
    def __init__(self, message: str = "Entity already exists") -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class EntityNotFound(Exception):
    def __init__(
        self, message: str = "Entity not found", data: Dict[str, Any] | None = None
    ) -> None:
        self.message: str = message
        self.data: Dict[str, Any] | None = data
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"{self.message} - {self.data}" if self.data else self.message


class EntityNotCreated(Exception):
    def __init__(self, message: str = "Entity not created") -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class ForbiddenOperation(Exception):
    def __init__(self, message: str = "Forbidden operation") -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class SubscriptionNotActive(Exception):
    def __init__(self, message: str = "Subscription is not active") -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class SubscriptionAlreadyCanceled(Exception):
    def __init__(self, message: str = "Subscription has already been canceled") -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


class UnverifiedEmailError(Exception):
    def __init__(
        self, message: str = "Email must be verified to create a virtual lab"
    ) -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message

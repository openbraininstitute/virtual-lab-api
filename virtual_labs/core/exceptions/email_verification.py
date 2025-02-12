class EmailVerificationException(Exception):
    def __init__(self, message: str = "Email verification error") -> None:
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message

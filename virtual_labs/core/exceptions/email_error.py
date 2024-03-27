from dataclasses import dataclass


@dataclass
class EmailError(Exception):
    message: str
    detail: str | None

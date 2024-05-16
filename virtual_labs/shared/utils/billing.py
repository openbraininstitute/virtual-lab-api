def amount_to_float(amount: int) -> float:
    return amount // 100 + amount % 100 / 100


def amount_to_cent(number: float) -> int:
    """Converts a dollar amount to cents"""

    return int(number * 100)

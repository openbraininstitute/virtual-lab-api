from random import choice
from string import ascii_uppercase, digits


def gen_random_string(length: int = 10) -> str:
    return "".join(choice(ascii_uppercase + digits) for _ in range(length))

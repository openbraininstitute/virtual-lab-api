from typing import List

from virtual_labs.core.exceptions.generic_exceptions import UserNotInList


def is_user_in_list(list_: List[str], user_id: str) -> bool:
    if user_id not in list_:
        raise UserNotInList("User not found in the list")
    return True

from typing import List, TypeVar

T = TypeVar("T")


def uniq_list(array: List[T]) -> List[T]:
    return list(set(array))

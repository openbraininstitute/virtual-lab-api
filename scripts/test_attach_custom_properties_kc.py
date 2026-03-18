# test update_user_custom_property

import asyncio
from uuid import UUID

from virtual_labs.repositories.user_repo import UserMutationRepository


async def main():
    user_mutation_repo = UserMutationRepository()
    await user_mutation_repo.update_user_custom_properties(
        user_id=UUID("32f9525f-5f3c-42f5-bcff-1195f26810fb"),
        properties=[
            ("plan", "pro", "unique"),
            ("virtual_lab_id", "32f9525f-5f3c-42f5-bcff-1195f2681aaa", "multiple"),
            ("role", "admin", "unique"),
        ],
    )


if __name__ == "__main__":
    asyncio.run(main())

from typing import List

project_member_acls: List[str] = [
    "files/write",
    "resources/write",
    "resources/read",
    "views/query",
    "views/write",
]

project_admin_acls: List[str] = [
    *project_member_acls,
    "projects/write",  # this will allow deprecation too (which is deletion in our case)
    "projects/read",
    "projects/delete",  # this will allow strict deletion
]

virtual_lab_admin_acls: List[str] = [
    *project_admin_acls,
    "organizations/read",
    "organizations/write",
    "organizations/create",
    # TODO: we should also request delta to add "organizations/delete"
    # TODO: also allow deprecation of an organization
]

virtual_lab_member_acls: List[str] = [*project_member_acls]

# TODO: to delete, just for info
all_acls = [
    "version/read",
    "acls/read",
    "acls/write",
    "events/read",
    "files/write",
    "organizations/create",
    "organizations/read",
    "organizations/write",
    "permissions/read",
    "permissions/write",
    "projects/create",
    "projects/read",
    "projects/write",
    "projects/delete",
    "realms/read",
    "realms/write",
    "resolvers/write",
    "resources/read",
    "resources/write",
    "schemas/write",
    "views/query",
    "views/write",
    "storages/write",
    "quotas/read",
    "supervision/read",
    "typehierarchy/write",
    "export/run",
]

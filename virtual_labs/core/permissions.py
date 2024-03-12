from typing import List

project_member_acls: List[str] = [
    "files/write",
    "resources/write",
    "resources/read",
    "views/query",
    "views/write",
    "archives/write",
]
project_admin_acls: List[str] = [
    *project_member_acls,
    "projects/write",
    "projects/read",
]

virtual_lab_admin_acls: List[str] = [
    *project_admin_acls,
    "organizations/read" "organizations/write" "organizations/create",
]
virtual_lab_member_acls: List[str] = []

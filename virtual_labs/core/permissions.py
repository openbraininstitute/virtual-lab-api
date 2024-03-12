from typing import List

project_member: List[str] = [
    "files/write",
    "resources/write",
    "resources/read",
    "views/query",
    "views/write",
    "archives/write",
]
project_admin: List[str] = [
    *project_member,
    "projects/write",
    "projects/read",
]

virtual_lab_admin: List[str] = [
    *project_admin,
    "organizations/read" "organizations/write" "organizations/create",
]
virtual_lab_member: List[str] = []

# Courses Provisionig

## Relationships

- Institution `1 ──── *` Course: Many courses can belong to one institution.
- VirtualLab `1 ──── 1` Course: Each vlab has at most one course (unique FK).
- Project `1 ──── 1` Course: Each course has one template project (unique FK).

## Course Lifecycle (status)

DRAFT → ACTIVE → VOIDED

- Draft can also be voided directly.

## Mutability Rules

- **DRAFT** → fully mutable (fields + status transitions)
- **ACTIVE** → immutable fields, can only transition to VOIDED
- **VOIDED** → fully immutable

## Business Rules

- The admin must create the institution (if it doesn't exist) before creating a course that references it.
- Only vlab service admins can create courses and institutions.
- The virtual lab assigned to a course must be owned by the `MULTIPLE_VLABS_ALLOWED_USER_ID` user (configured in settings).
- The template project must belong to the associated virtual lab.

# Courses Provisionig

## Relationships

```
                        ┌─────────────┐
                        │ Institution │
                        └──────┬──────┘
                               │ 1
                               │
                               *
┌─────────────┐         ┌─────────────┐
│ Virtual Lab │1───────*│   Course    │
└─────────────┘         └──────┬──────┘
                               │ 1
                               │
                               *
                        ┌─────────────┐
                        │    Seat     │
                        └──────┬──────┘
                               │ 0..1
                               │
                               1
┌─────────────┐         ┌─────────────┐
│   Project   │1───────1│  Enrolment  │
└─────────────┘         └─────────────┘
```

## Course Lifecycle (status)

DRAFT → ACTIVE → VOIDED

- Draft can also be voided directly.

## Mutability Rules

- **DRAFT** → fully mutable (fields + status transitions)
- **ACTIVE** → immutable fields, can only transition to VOIDED
- **VOIDED** → fully immutable

## Business Rules

- Only vlab service admins can create courses and institutions.
- The admin must create the institution (if it doesn't exist) before creating a course that references it.
- The virtual lab assigned to a course must be owned by the `MULTIPLE_VLABS_ALLOWED_USER_ID` user (configured in settings).
- The template project must belong to the associated virtual lab.
- Only active courses can be provisioned with seats.
- To activate a course, all dates must be set (`start_date < last_drop_date < end_date`).

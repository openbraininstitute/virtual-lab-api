# Courses – Entity Relationships

```
┌─────────────────────────────────────┐
│           Institution               │
├─────────────────────────────────────┤
│  id          : UUID (PK)           │
│  name        : String(250) UNIQUE  │
│  contact_email: String(255)        │
│  created_at  : DateTime            │
│  updated_at  : DateTime            │
└──────────────────┬──────────────────┘
                   │
                   │ 1
                   │
                   ▼ *
┌─────────────────────────────────────┐         1:1          ┌─────────────────────────────────────┐
│             Course                  │◄─────────────────────►│          VirtualLab                 │
├─────────────────────────────────────┤                       ├─────────────────────────────────────┤
│  id               : UUID (PK)      │                       │  id              : UUID (PK)        │
│  virtual_lab_id   : UUID (FK, UQ)  │──────────────────────►│  name            : String(250)      │
│  institution_id   : UUID (FK)      │──┐                    │  description     : Text             │
│  template_project_id: UUID (FK,UQ) │  │                    │  owner_id        : UUID             │
│  status           : CourseStatus   │  │                    │  entity          : String           │
│  start_date       : Date?          │  │                    │  deleted         : Boolean          │
│  end_date         : Date?          │  │                    │  ...                                │
│  last_drop_date   : Date?          │  │                    └─────────────────────────────────────┘
│  created_at       : DateTime       │  │
│  updated_at       : DateTime       │  │                    ┌─────────────────────────────────────┐
└─────────────────────────────────────┘  │         1:1       │            Project                  │
                                         │  ────────────────►├─────────────────────────────────────┤
                                         │                   │  id   : UUID (PK)                   │
                                         └──────────────────►│  ...  (template project)            │
                                                             └─────────────────────────────────────┘

Relationships:
─────────────────────────────────────────────────────
  Institution  1 ──── * Course     Many courses can belong to one institution
  VirtualLab   1 ──── 1 Course     Each vlab has at most one course (unique FK)
  Project      1 ──── 1 Course     Each course has one template project (unique FK)

Course Lifecycle (status):
─────────────────────────────────────────────────────
  DRAFT ───► ACTIVE ───► VOIDED
    │                       ▲
    └───────────────────────┘  (draft can also be voided directly)

Mutability Rules:
  • DRAFT  → fully mutable (fields + status transitions)
  • ACTIVE → immutable fields, can only transition to VOIDED
  • VOIDED → fully immutable
```

## Key Takeaways

- **Institution → Course** is one-to-many: an institution can have multiple courses, but each course belongs to exactly one institution.
- **VirtualLab → Course** is one-to-one: enforced by a `UNIQUE` constraint on `virtual_lab_id` in the `course` table. The VirtualLab model uses `uselist=False` on its `course` relationship.
- **Project → Course** is also one-to-one (the "template project"): enforced by a `UNIQUE` constraint on `template_project_id`.
- Activation requires all dates set and ordered: `start_date < last_drop_date < end_date`.

## Business Rules

- The admin must create the institution (if it doesn't exist) before creating a course that references it.
- Only vlab service admins can create courses and institutions.
- The virtual lab assigned to a course must be owned by the `MULTIPLE_VLABS_ALLOWED_USER_ID` user (configured in settings).

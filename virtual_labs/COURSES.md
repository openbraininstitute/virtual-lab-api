# Courses Provisioning

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


## Course Lifecycle

### Provisioning

1. OBI admin creates a virtual lab belonging to `obi-virtual-lab`.
   `POST /virtual-labs`
2. OBI admin creates a template project for that virtual lab.
   `POST /virtual-labs/{vlab_id}/projects`
3. OBI admin creates a course pointing to the virtual lab and template project.
   `POST /courses`
4. OBI admin sets `start_date`, `last_drop_date`, and `end_date`.
   `PATCH /courses/{course_id}`
5. OBI admin activates the course (all dates must be set).
   `POST /courses/{course_id}/activate`
6. OBI admin invites faculty as virtual lab admin.
   `POST /virtual-labs/{vlab_id}/invites`
7. OBI admin provisions seats (only active courses can be provisioned).
   `POST /seats/provision`

### Enrolment

1. Faculty assigns available seats to students (identified by student id + email).
   `POST /seats/courses/{course_id}/assign`
   This creates an enrolment and a project per student and sends an invite email.

2. Student claims the enrolment, storing their `user_id`.
   `POST /courses/{course_id}/claim`

3. On login (after `start_date`, before `end_date`), the student's enrolment is activated (added to KC groups).
   `POST /courses/activate-enrolments`

### Dropping

Faculty can drop a student and recover the seat if all conditions are met:
- `seat.previously_dropped == False`
- `now < course.last_drop_date`
- The student's project has spent fewer than 50 credits.

`POST /seats/courses/{course_id}/drop`

When dropped, the student's project budget is depleted and the student is removed from KC groups (vlab and project).

### Course Expiry

A daily cronjob checks courses whose `end_date` has passed, drops every remaining student, and depletes all credits from all projects and the virtual lab.

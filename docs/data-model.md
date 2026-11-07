# Environment Management: Data Model

This is the data model for environment inventory and booking. It is agreed before the website is built and
extends the entities that already exist (`Environment`, `Variable`, and the Flow Explorer's `System`).

## Agreed rules

| Topic | Decision |
| ----- | -------- |
| What gets booked | A whole **Environment**. Individual services are not booked. |
| Who books | A **Project**. Users act on behalf of a project, and the booking belongs to the project. |
| Approval | Each environment has an **approver group**. Any one member of that group can approve or reject. |
| Sharing | An environment can be shared: several projects can hold bookings for overlapping periods, up to the environment's capacity. |

## Overview

```
Group 1─* GroupMember *─1 User 1─* ProjectMember *─1 Project
  │                                                   │
  │ approves                                          │ books
  ▼                                                   ▼
Environment 1──────────────────────────────* BookingRequest 1─* BookingStatusHistory
  │  (approver_group_id)                              │
  ├─* ServiceInstance *─1 System                      └─0..1 Approval (decision by a group member)
  │        └─* Deployment
  ├─* Variable
  ├─* MaintenanceWindow
  ├─* DataRefresh
  └─* EnvironmentIssue
```

## 1. Inventory

### System *(exists: `systems`)*
The logical application or component, such as Billing or Polisy. There is one record per application,
whatever environments it runs in.

| Field | Type | Notes |
| ----- | ---- | ----- |
| id | string PK | Existing |
| name | string, unique | |
| type, layer, domain, owner, notes | | Existing |
| environment | string | **Deprecated.** Replaced by `ServiceInstance`. |

### Environment *(exists: extend `environments`)*

| Field | Type | Notes |
| ----- | ---- | ----- |
| id | int PK | |
| name | string, unique | e.g. `SIT1`, `UAT2` |
| tier | enum | `DEV`, `SIT`, `UAT`, `PREPROD`, `PERF`, `PROD` |
| status | enum | `available`, `maintenance`, `decommissioned` |
| description / purpose | text | |
| owner_group_id | FK → Group | The team that runs the environment |
| approver_group_id | FK → Group | Any one member can approve bookings |
| is_bookable | bool | False for PROD and similar |
| max_concurrent_projects | int, default 1 | Sharing capacity. 1 means a single project at a time. |
| max_booking_days | int, nullable | Longest booking allowed |
| created_at, updated_at | timestamptz | |

### ServiceInstance *(new)*
One System deployed in one Environment.

| Field | Type | Notes |
| ----- | ---- | ----- |
| id | int PK | |
| environment_id | FK → Environment | |
| system_id | FK → System | Unique together with `environment_id` |
| version | string | Current build or version |
| base_url, host | string | Metadata only. Never store credentials here. |
| status | enum | `up`, `down`, `degraded`, `unknown` |
| last_deployed_at, last_health_check_at | timestamptz | |
| notes | text | |

### Variable *(exists)*
Key/value configuration for an environment. Optionally add `service_instance_id` for variables that belong to
one service.

## 2. People, groups and projects

### User

| Field | Type | Notes |
| ----- | ---- | ----- |
| id | int PK | |
| username | string, unique | Matches `X-Forwarded-User` from SSO |
| display_name, email | string | |
| is_active | bool | |

### Group
A set of users. Used for approver groups and environment owner teams.

| Field | Type | Notes |
| ----- | ---- | ----- |
| id | int PK | |
| name | string, unique | e.g. `UAT Environment Managers` |
| sso_group | string, nullable | If set, membership comes from `X-Forwarded-Groups` and is not kept in the database |
| description | text | |

### GroupMember
`group_id` FK, `user_id` FK, unique together. Not needed for groups whose membership comes from SSO.

### Project *(new: the entity that books)*

| Field | Type | Notes |
| ----- | ---- | ----- |
| id | int PK | |
| code | string, unique | e.g. `PRJ-CLAIMS-2027` |
| name | string | |
| description | text | |
| status | enum | `planned`, `active`, `on_hold`, `closed`. Only `active` projects can book. |
| start_date, end_date | date | |
| cost_centre | string, nullable | For reporting and chargeback |
| created_at, updated_at | timestamptz | |

### ProjectMember

| Field | Type | Notes |
| ----- | ---- | ----- |
| project_id | FK → Project | |
| user_id | FK → User | Unique together with `project_id` |
| role | enum | `lead` (can request and cancel bookings) or `member` (uses the environment) |

## 3. Booking

### BookingRequest

| Field | Type | Notes |
| ----- | ---- | ----- |
| id | int PK | |
| reference | string, unique | e.g. `BK-2026-0142` |
| project_id | FK → Project | **The owner of the booking** |
| environment_id | FK → Environment | |
| requested_by | FK → User | A lead of the project. Kept for audit. |
| start_at, end_at | timestamptz | `end_at > start_at` |
| purpose | text | |
| test_type | enum | `functional`, `regression`, `integration`, `performance`, `uat`, `demo`, `other` |
| status | enum | See the flow below |
| created_at, updated_at | timestamptz | |

Status flow:

```
draft → submitted → approved → active → completed
             │           │
             ├→ rejected └→ cancelled
             └→ cancelled           (approved and not started by end_at → expired)
```

`active` and `completed` can be worked out from the clock for approved bookings. Store them only if the
website needs to filter on them cheaply.

### Approval

| Field | Type | Notes |
| ----- | ---- | ----- |
| id | int PK | |
| booking_id | FK → BookingRequest | One decision per submission |
| approver_id | FK → User | Must be a member of the environment's `approver_group` at decision time |
| decision | enum | `approved`, `rejected` |
| comment | text | Required when the decision is `rejected` |
| decided_at | timestamptz | |

### BookingStatusHistory
`booking_id`, `from_status`, `to_status`, `changed_by`, `changed_at`, `reason`.

### Booking rules

1. **Capacity.** At any point in time, the number of `approved` bookings for an environment must not exceed
   `max_concurrent_projects`. Check this when a booking is submitted and again when it is approved, inside the
   same transaction as the status change.
2. **One booking per project per environment per period.** A project cannot hold two overlapping approved
   bookings on the same environment. Enforce this in PostgreSQL with an exclusion constraint on
   `(project_id, environment_id, tstzrange(start_at, end_at))` where `status = 'approved'`.
3. **Approver.** Any member of `environment.approver_group` can decide. The first decision wins. A user cannot
   approve a booking they requested.
4. **Who can request.** Only a `lead` of an `active` project, and only for an environment where `is_bookable` is
   true and `status` is `available`.
5. **Maintenance.** A booking period that overlaps a `planned` maintenance window triggers a warning at
   submission. An `unplanned` outage notifies all affected projects.
6. **Length.** `end_at - start_at` must not exceed `max_booking_days`, if it is set.
7. **Access.** While a booking is active, every member of the booking's project counts as a user of the
   environment.

## 4. Operations

| Entity | Fields |
| ------ | ------ |
| **MaintenanceWindow** | id, environment_id, service_instance_id (nullable), type (`planned`/`unplanned`), start_at, end_at, impact, reason, created_by |
| **Deployment** | id, service_instance_id, version, deployed_by, deployed_at, status (`succeeded`/`failed`/`rolled_back`), release_ref |
| **DataRefresh** | id, environment_id, source (e.g. masked PROD copy), refreshed_at, refreshed_by, notes |
| **EnvironmentIssue** | id, environment_id, service_instance_id (nullable), title, severity, status (`open`/`resolved`), raised_by, external_ref (e.g. Jira key), created_at, resolved_at |

## 5. Cross-cutting

- **AuditLog** *(exists)*: records every create, update and status change.
- **Notification**: id, user_id, type (`booking_submitted`, `booking_approved`, `booking_rejected`,
  `booking_expiring`, `outage`), entity_type, entity_id, created_at, read_at. Recipients: approver group
  members for submissions, and project members for decisions and outages.

## Suggested build order

1. User, Group, Project and ProjectMember, plus the extended Environment fields.
2. ServiceInstance, linked to the existing `systems` table.
3. BookingRequest, Approval and status history, with the capacity and overlap rules.
4. MaintenanceWindow, and a calendar view that combines bookings and outages per environment.
5. Deployment, DataRefresh, EnvironmentIssue and Notification.

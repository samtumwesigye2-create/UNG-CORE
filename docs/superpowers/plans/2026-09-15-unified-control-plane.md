# UNG-CORE Unified Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the missing unified resource, job, report, storage, compatibility, authorization, service-control, and operator-command capabilities into UNG-CORE.

**Architecture:** Extend the existing FastAPI/SQLAlchemy control plane with focused models/services/routes. Reuse existing scheduler, operator, audit, telemetry, gateway, event-delivery and IAM boundaries; CORE stores control-plane metadata and delegates domain ownership.

**Tech Stack:** Python, FastAPI, SQLAlchemy async ORM, PostgreSQL-compatible persistence, pytest.

**Spec:** `docs/superpowers/specs/2026-09-15-unified-control-plane-design.md`

## Global Constraints
- UNG-CORE remains the platform foundation; domain systems retain business ownership.
- JANUS/IAM remains authoritative for identity and access.
- NEXUS remains authoritative for interoperability; PULSAR/Data Relay for events; VAULT for cryptography; NOVA for analytics.
- New privileged operations must be authorized and audited.
- Existing scheduler/operator/control-center behavior must remain intact.
- Storage abstraction uses logical references; it does not claim IBM i single-level storage semantics.
- Compatibility contracts provide semantic-version/API/event/schema compatibility, not RPG/COBOL binary emulation.

---

### Task 1: Resource/Object Catalog

**Files:**
- Create: `app/models/resource_catalog.py`
- Create: `app/services/resource_catalog.py`
- Create: `app/api/resource_routes.py`
- Modify: `app/main.py`
- Test: `tests/test_resource_catalog.py`

**Interfaces:**
- Produces `register_resource(db, payload)`, `find_resources(db, query, resource_type=None)`, `get_resource(db, resource_id)`.
- Resource fields: `resource_id`, `resource_type`, `system_key`, `name`, `version`, `health_state`, `metadata_json`, `dependencies_json`, `controllable`, timestamps.

- [ ] Write failing tests proving registration, duplicate-ID rejection, text/type search, detail lookup and unknown-resource 404.
- [ ] Run `pytest tests/test_resource_catalog.py -v`; expect failures because catalog modules/routes do not exist.
- [ ] Implement `ResourceRecord` SQLAlchemy model with stable string primary key and indexed type/system/name fields.
- [ ] Implement service functions with deterministic search ordering and duplicate conflict handling.
- [ ] Add authenticated `/v1/resources`, `/v1/resources/find`, `/v1/resources/{resource_id}` routes using `ung.core.registry.read/write` permissions.
- [ ] Import model and include router in `app/main.py`.
- [ ] Run `pytest tests/test_resource_catalog.py -v`; expect PASS.
- [ ] Commit with `feat: add unified resource catalog`.

### Task 2: Consolidated Job Registry

**Files:**
- Create: `app/models/job_registry.py`
- Create: `app/services/job_registry.py`
- Create: `app/api/job_registry_routes.py`
- Modify: `app/main.py`
- Test: `tests/test_job_registry.py`

**Interfaces:**
- Produces `upsert_job(db, payload)`, `transition_job(db, job_id, new_state, detail=None)`, `list_jobs(db, state=None, system_key=None)`.
- Allowed states: `queued`, `running`, `succeeded`, `failed`, `cancelled`; terminal states cannot transition back to running.

- [ ] Write failing tests for interactive/batch/scheduled job registration, filtering, valid transition, terminal-state conflict and failure detail.
- [ ] Run `pytest tests/test_job_registry.py -v`; expect missing implementation failures.
- [ ] Implement job model with owner/system/type/state/progress/timestamps/resource-usage/failure fields.
- [ ] Implement transition validation and list service; scheduled jobs reference existing scheduler IDs without replacing scheduler execution.
- [ ] Add `/v1/jobs/registry` read/write endpoints guarded by `ung.core.jobs.read/write`.
- [ ] Register model/router in `app/main.py`.
- [ ] Run targeted tests; expect PASS.
- [ ] Commit with `feat: add consolidated job registry`.

### Task 3: Report/Output Spool

**Files:**
- Create: `app/models/report_spool.py`
- Create: `app/services/report_spool.py`
- Create: `app/api/report_spool_routes.py`
- Modify: `app/main.py`
- Test: `tests/test_report_spool.py`

**Interfaces:**
- Produces `enqueue_output`, `list_outputs`, `get_output`, `mark_delivered`, `expire_output`, `delete_output`.
- Stores metadata plus `storage_ref`; binary payloads are not stored in the spool table.

- [ ] Write failing lifecycle tests: enqueue, list by owner/system/type, inspect, deliver, expire, delete, forbidden transition.
- [ ] Run targeted tests and verify failure.
- [ ] Implement `ReportSpoolEntry` with output ID, owner, system, output type, title, MIME type, storage reference, state, retention timestamp and audit timestamps.
- [ ] Implement lifecycle service with `queued -> delivered|expired` and deletion authorization boundary.
- [ ] Add `/v1/reports` endpoints guarded by `ung.core.reports.read/write`.
- [ ] Register model/router and run tests; expect PASS.
- [ ] Commit with `feat: add report output spool`.

### Task 4: Logical Storage Registry

**Files:**
- Create: `app/models/storage_registry.py`
- Create: `app/services/storage_registry.py`
- Create: `app/api/storage_routes.py`
- Modify: `app/main.py`
- Test: `tests/test_storage_registry.py`

**Interfaces:**
- Produces `register_storage_ref`, `resolve_storage_ref`, `list_storage_refs`.
- Supported initial schemes: `postgres`, `object`, `archive`; references contain no credentials.

- [ ] Write failing tests for each supported scheme, invalid scheme, secret-looking URI rejection and lookup.
- [ ] Run targeted tests; expect failure.
- [ ] Implement storage-reference model and validation that rejects embedded username/password/query secrets.
- [ ] Implement registry service returning logical metadata rather than provider credentials.
- [ ] Add `/v1/storage` read/write endpoints with `ung.core.storage.read/write`.
- [ ] Register and test; expect PASS.
- [ ] Commit with `feat: add logical storage registry`.

### Task 5: Compatibility Contract Registry

**Files:**
- Create: `app/models/compatibility.py`
- Create: `app/services/compatibility.py`
- Create: `app/api/compatibility_routes.py`
- Modify: `app/main.py`
- Test: `tests/test_compatibility.py`

**Interfaces:**
- Produces `register_contract`, `evaluate_transition(current_version, candidate_version, policy)`, `update_contract_version`.
- Policies: `major-stable`, `minor-stable`, `exact`; versions use numeric `MAJOR.MINOR.PATCH`.

- [ ] Write failing tests for valid semantic versions, malformed versions, compatible minor/patch changes and rejected breaking changes under each policy.
- [ ] Run targeted tests; expect failure.
- [ ] Implement contract model for API/event/schema/command/resource contracts and lifecycle state.
- [ ] Implement strict semantic-version parser and transition rules without adding a new dependency.
- [ ] Add `/v1/contracts` endpoints guarded by `ung.core.contracts.read/write`.
- [ ] Register and test; expect PASS.
- [ ] Commit with `feat: add platform compatibility contracts`.

### Task 6: Resource Authorization and Service Lifecycle Control

**Files:**
- Create: `app/services/resource_authorization.py`
- Create: `app/services/service_control.py`
- Create: `app/api/service_control_routes.py`
- Modify: `app/main.py`
- Test: `tests/test_service_control.py`

**Interfaces:**
- Produces `authorize_resource_action(principal, resource, action)` and `request_service_transition(db, principal, resource_id, action)`.
- Actions: `start`, `stop`, `restart`; only catalog resources with `controllable=True` qualify.

- [ ] Write failing tests for admin permission, explicit resource permission, non-controllable resource rejection, invalid action, successful transition request and audit-on-failure/success.
- [ ] Run targeted tests; expect failure.
- [ ] Implement resource/action permission matching using existing `Principal` and `ung.core.admin` override; do not create users locally.
- [ ] Implement service-control adapter boundary that records requested/current/resulting state and never writes foreign service databases directly.
- [ ] Route `/v1/services/{resource_id}/{action}` through authorization and existing audit service.
- [ ] Register and test; expect PASS.
- [ ] Commit with `feat: add authorized service lifecycle control`.

### Task 7: Unified UNG Operator Command Dispatcher

**Files:**
- Create: `app/services/operator_commands.py`
- Create: `app/api/command_routes.py`
- Modify: `app/main.py`
- Modify: `app/api/operator_routes.py`
- Test: `tests/test_operator_commands.py`

**Interfaces:**
- Produces `execute_command(db, principal, command_text)` returning `{command, ok, data, error}`.
- Commands: `STATUS`, `JOBS`, `SERVICES`, `REPORTS`, `FIND`, `SHOW`, `LOGS`, `HEALTH`, `EVENTS`, `USERS`, `SESSIONS`, `STORAGE`, `DATABASES`, `QUEUES`, `CONNECTIONS`, `START`, `STOP`, `RESTART`, `AUDIT`, `SIGNOFF`.

- [ ] Write failing parser/dispatch tests for every command, argument validation, case-insensitivity, unknown command, permission denial and audit recording.
- [ ] Run targeted tests; expect failure.
- [ ] Implement strict token parser accepting optional leading `UNG`; map read commands to existing/new services and lifecycle commands to Task 6.
- [ ] Implement `SIGNOFF` as session-termination response through the existing auth boundary; do not delete JANUS identities.
- [ ] Add `POST /v1/operator/commands` and expose command capability metadata from `/v1/operator/capabilities`.
- [ ] Register router and run targeted tests; expect PASS.
- [ ] Commit with `feat: add unified UNG operator commands`.

### Task 8: Control Center Integration and Full Regression

**Files:**
- Modify: `app/api/operator_routes.py`
- Modify: `app/api/control_center_routes.py`
- Modify: `README.md`
- Test: `tests/test_operator_control_plane.py`

**Interfaces:**
- Consumes all prior task services.
- Produces a single permission-aware workspace/dashboard summary for resources, jobs, reports, storage, contracts and service controls.

- [ ] Write failing integration tests proving dashboard summaries appear only with matching permissions and existing dashboard fields remain unchanged.
- [ ] Run targeted integration test; expect failure.
- [ ] Extend operator workspace/dashboard navigation and summaries without replacing current readiness, gateway, telemetry, alerts, incidents, approvals, scheduler, audit or resilience sections.
- [ ] Update README with the new endpoints, command vocabulary, authorization model and explicit domain-ownership boundaries.
- [ ] Run `pytest -q`; all existing and new tests must PASS.
- [ ] Run an application import/startup smoke test: `python -c "from app.main import app; print(app.title)"`; expect the configured app title and exit code 0.
- [ ] Commit with `feat: complete unified UNG control plane`.

## Self-Review
Spec coverage: resource catalog, jobs, spool, storage abstraction, compatibility, JANUS-backed authorization, service control, command interface, error boundaries, audit and regression testing are each assigned to a task. No domain system is moved into CORE. The plan contains no deferred implementation placeholders. Interfaces use stable names across dependent tasks.
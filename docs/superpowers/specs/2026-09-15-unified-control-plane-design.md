# UNG-CORE Unified Control Plane Design

## Goal
Extend UNG-CORE into the common operational control plane for the UNG ecosystem without absorbing responsibilities owned by JANUS, NEXUS, PULSAR, VAULT, NOVA, VECTOR, UGASHIP, or other domain systems.

## Architecture
UNG-CORE remains the platform foundation and adds six bounded capabilities: a resource/object catalog, consolidated job management, report/output spool management, storage abstraction, compatibility contracts, and a unified operator command interface. Existing scheduler, operator, control-center, telemetry, alerting, recovery, gateway, event-delivery, approval, audit, and command-history components are reused rather than replaced.

JANUS remains authoritative for identity and access. NEXUS remains authoritative for interoperability. PULSAR remains authoritative for event/data relay. VAULT remains authoritative for cryptographic protection. NOVA remains authoritative for analytics. Domain systems retain their business data and workflows.

## Resource Catalog
Every manageable platform resource can be registered with a stable resource ID, type, owning system, human-readable name, version, health state, metadata, and dependency references. CORE exposes search and detail operations backing `UNG FIND` and `UNG SHOW`. Registration does not transfer ownership of the underlying resource to CORE.

## Job Management
CORE consolidates visibility into interactive, scheduled, batch, queue-worker, and long-running jobs. The job view records stable job ID, owner/system, type, state, start/end timestamps, progress, resource usage when reported, and failure details. Existing scheduler functionality remains the execution source for scheduled jobs. `UNG JOBS` is the common operational view.

## Report Spool
CORE provides a registry/queue for generated operational outputs such as reports, statements, manifests, exports, and PDFs. It stores metadata and a storage reference rather than requiring large output binaries in the CORE database. Operators can list, inspect, mark delivered, expire, or remove outputs subject to authorization and retention rules. `UNG REPORTS` is the operator entry point.

## Storage Abstraction
CORE defines logical storage references independent of a specific backend. PostgreSQL, object storage, archive storage, or another approved provider can be addressed through a common storage-reference contract. This is not IBM i single-level storage and does not pretend memory and disk are one address space; it gives UNG applications a stable managed-storage interface.

## Compatibility Contracts
Registered APIs, events, schemas, commands, and resource types can declare contract name, semantic version, compatibility policy, and lifecycle state. CORE rejects unsupported breaking-version transitions at the contract-management boundary. This provides a platform compatibility contract without attempting RPG/COBOL binary emulation.

## Authorization
Every privileged resource, job, report, storage, and service-control operation passes through the existing CORE security boundary and JANUS/IAM contract. Authorization is resource/action based. CORE does not create a second identity database. Destructive and service-control actions are audited.

## Operator Commands
The command layer exposes a consistent API/CLI vocabulary: `UNG STATUS`, `UNG JOBS`, `UNG SERVICES`, `UNG REPORTS`, `UNG FIND`, `UNG SHOW`, `UNG LOGS`, `UNG HEALTH`, `UNG EVENTS`, `UNG USERS`, `UNG SESSIONS`, `UNG STORAGE`, `UNG DATABASES`, `UNG QUEUES`, `UNG CONNECTIONS`, `UNG START`, `UNG STOP`, `UNG RESTART`, `UNG AUDIT`, and `UNG SIGNOFF`.

Commands are thin control-plane operations over existing/new CORE services; they do not bypass authorization or directly manipulate foreign databases. START/STOP/RESTART target only registered controllable services and require privileged authorization plus audit recording.

## Data Flow
Domain systems and platform services register resources and publish health/job/output metadata to CORE. CORE persists control-plane metadata in PostgreSQL. Operator requests enter through authenticated API routes, are authorized, executed through the relevant service adapter, audited, and returned as structured results. Event delivery continues through the existing PULSAR/Data Relay contract.

## Error Handling
Unknown resources return not-found responses. Invalid state transitions return conflict responses. Unauthorized operations return access-denied responses without leaking protected metadata. Remote service failures are represented as dependency failures and do not corrupt local control-plane state. Service-control operations use explicit requested/current/resulting state and audit both success and failure.

## Testing
Each capability receives model/service/API tests. Tests cover registration/search, duplicate resource IDs, job state transitions, spool lifecycle, storage-reference validation, compatibility transition rules, authorization gates, command parsing/dispatch, destructive-operation audit records, and failure behavior. Existing tests must remain green.

## Success Criteria
An authorized operator can use one UNG-CORE interface to discover resources, inspect system health, view jobs and reports, inspect storage/queues/connections, execute authorized service lifecycle actions, inspect audit/events, and safely sign off. No domain-system ownership is duplicated, existing CORE control-plane functions remain intact, and all new privileged operations are authorized and audited.
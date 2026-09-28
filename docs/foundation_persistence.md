# Foundation Persistence

UNG-CORE now has a durable state store for restart-safe foundation configuration and recovery metadata.

The `foundation_state` table stores JSON payloads by namespace/key and records updater identity plus timestamp. It is intended for durable control-plane state such as calibration/configuration snapshots, service metadata, update checkpoints, and recovery state.

Routes:

- `PUT /v1/foundation/state/{namespace}/{state_key}`
- `GET /v1/foundation/state/{namespace}/{state_key}`
- `GET /v1/foundation/state/{namespace}`

Writes use the existing `ung.core.config.write` permission and reads use `ung.core.config.read`.

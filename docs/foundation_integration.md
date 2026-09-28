# Foundation Integration Layer

The previously implemented foundation services are composed into a single shared FoundationRuntime and exposed through authenticated UNG-CORE routes.

## Runtime composition

FoundationRuntime owns shared instances of time synchronization, observability, calibration/configuration, fault supervision, OTA/rollback, device identity, MLOps, sensor self-test, resource scheduling, schema registry, event bus, replay, scenario orchestration, storage lifecycle, fleet management, predictive maintenance, workflow orchestration, geospatial state, HMI state, API policy, and disaster recovery.

## Initial API integration

- GET /v1/foundation/status
- POST /v1/foundation/time-sync/sample
- POST /v1/foundation/faults
- DELETE /v1/foundation/faults/{component}/{code}
- POST /v1/foundation/metrics/gauge
- POST /v1/foundation/metrics/counter
- GET /v1/foundation/hmi

All write routes remain behind existing UNG permission checks. Hardware/platform adapters stay separate from the core runtime.

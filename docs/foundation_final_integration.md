# Foundation Final Integration

This phase closes the shared-foundation integration sequence.

## Event-driven durability

Important fault-state mutations checkpoint immediately in addition to the periodic background checkpoint. This reduces the restart window for degraded-mode and recovery state.

## Cross-system adapters

UNG-CORE now publishes normalized adapter profiles for DRACO, WAVE, NEXUS, NAVSTAR and CAD/manufacturing. The profiles define which shared foundation capabilities each system consumes and the authenticated read/write API surfaces used to connect them. Unknown UNG systems receive a conservative generic profile instead of requiring duplicate foundation implementations.

## Acceptance and rollout gate

The final acceptance contract checks runtime health, restart hydration, observability, service/RBAC policy, cross-system adapter availability, OTA rollback behavior and the production-readiness contract. CI runs these acceptance tests before merge.

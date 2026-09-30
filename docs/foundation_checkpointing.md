# Foundation Runtime Checkpointing

UNG-CORE now has a restart-safe bridge between the in-memory `FoundationRuntime` and the persistent `foundation_state` store.

The runtime checkpoint captures selected control-plane state that is meaningful across restarts, including:

- active fault state and degraded-mode reconstruction
- HMI system mode reconstruction
- geospatial map-version provenance
- OTA current/previous version metadata
- observability counters and gauges

At startup, UNG-CORE hydrates the shared foundation runtime after database tables are available. During runtime, a periodic checkpoint task writes the current state back to the database. Shutdown also performs a final checkpoint when possible.

Ephemeral data such as monotonic timestamps, active asyncio queues, transient trace buffers, and hardware handles are intentionally not restored.

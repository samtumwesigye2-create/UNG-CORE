# UNG Foundation Tranche 1

This tranche implements the first five shared platform priorities in UNG-CORE.

## Included

1. **Authoritative time health** — normalizes PTP/GNSS/NTP adapter measurements into offset, drift, uncertainty, freshness, and quality state.
2. **Unified observability** — dependency-light counters, gauges, latency distributions, and trace events suitable for export into OpenTelemetry-compatible infrastructure.
3. **Configuration/calibration registry** — immutable, checksummed, versioned calibration records with explicit activation.
4. **Fault supervisor** — centralized fault state, dependency-aware degradation, and system-mode evaluation.
5. **OTA/rollback manager** — verified-artifact staging, compatibility checks, A/B-style boot verification, commit, and rollback state.

## Boundaries

- PTP, GNSS, NTP, TPM/HSM, bootloader, and actual A/B partition operations are platform adapters, not simulated here.
- OTA signature verification must be performed by the trusted platform verifier. The OTA manager consumes only the verification result.
- Observability exporters are intentionally separate so UNG-CORE remains dependency-light.
- These services are shared foundations for NEXUS, DRACO, WAVE, NAVSTAR, CAD/manufacturing, and other authorized UNG systems.

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FoundationAdapterProfile:
    system_key: str
    capabilities: tuple[str, ...]
    read_endpoints: tuple[str, ...]
    write_endpoints: tuple[str, ...]
    notes: str = ""


_BASE_READ = (
    "/v1/foundation/status",
    "/v1/foundation/hmi",
    "/v1/foundation/state/{namespace}",
)
_BASE_WRITE = (
    "/v1/foundation/time-sync/sample",
    "/v1/foundation/faults",
    "/v1/foundation/metrics/gauge",
    "/v1/foundation/metrics/counter",
    "/v1/foundation/state/{namespace}/{state_key}",
)


PROFILES: dict[str, FoundationAdapterProfile] = {
    "DRACO": FoundationAdapterProfile(
        "DRACO",
        ("time_sync", "observability", "calibration", "faults", "device_identity", "sensor_self_test", "replay", "storage", "fleet"),
        _BASE_READ,
        _BASE_WRITE,
        "Sensor/perception platform adapter; preserves calibrated timestamps and health provenance.",
    ),
    "WAVE": FoundationAdapterProfile(
        "WAVE",
        ("time_sync", "observability", "faults", "ota", "device_identity", "resource_scheduler", "storage", "fleet"),
        _BASE_READ,
        _BASE_WRITE,
        "Edge/network platform adapter for health, fleet identity, updates and runtime telemetry.",
    ),
    "NEXUS": FoundationAdapterProfile(
        "NEXUS",
        ("schemas", "event_bus", "api_policy", "observability", "replay", "storage", "disaster_recovery"),
        _BASE_READ,
        _BASE_WRITE,
        "Integration-layer adapter for canonical contracts, events, policy and provenance.",
    ),
    "NAVSTAR": FoundationAdapterProfile(
        "NAVSTAR",
        ("time_sync", "calibration", "faults", "geospatial", "replay", "observability"),
        _BASE_READ,
        _BASE_WRITE,
        "Navigation adapter for synchronized frames, map provenance and degraded navigation health.",
    ),
    "CAD": FoundationAdapterProfile(
        "CAD",
        ("schemas", "workflows", "storage", "observability", "replay", "disaster_recovery"),
        _BASE_READ,
        _BASE_WRITE,
        "CAD/manufacturing adapter for workflow state, schema contracts, storage and reproducibility.",
    ),
}


def adapter_profile(system_key: str) -> FoundationAdapterProfile:
    key = system_key.strip().upper()
    if key.startswith("UNG-"):
        key = key[4:]
    profile = PROFILES.get(key)
    if profile is not None:
        return profile
    return FoundationAdapterProfile(
        key,
        ("time_sync", "observability", "faults", "schemas", "storage"),
        _BASE_READ,
        _BASE_WRITE,
        "Generic UNG foundation adapter profile.",
    )


def serialize_profile(profile: FoundationAdapterProfile) -> dict:
    return {
        "system_key": profile.system_key,
        "capabilities": list(profile.capabilities),
        "read_endpoints": list(profile.read_endpoints),
        "write_endpoints": list(profile.write_endpoints),
        "notes": profile.notes,
    }

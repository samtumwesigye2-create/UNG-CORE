from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.security import require_permission
from app.schemas.contracts import Principal
from app.services.fault_supervisor import FaultSeverity
from app.services.foundation_acceptance import foundation_acceptance_report
from app.services.foundation_adapters import adapter_profile, serialize_profile
from app.services.foundation_checkpoint import checkpoint_runtime
from app.services.foundation_runtime import foundation_runtime
from app.services.time_sync import ClockSample

router = APIRouter(prefix="/v1/foundation", tags=["foundation"])

class ClockSampleIn(BaseModel):
    source: str
    source_time_ns: int
    received_monotonic_ns: int
    uncertainty_ns: int = Field(default=0, ge=0)
    local_wall_time_ns: int | None = None

class FaultIn(BaseModel):
    component: str
    code: str
    severity: str
    message: str = ""

class MetricIn(BaseModel):
    name: str
    value: float

class CounterIn(BaseModel):
    name: str
    amount: int = 1

@router.get("/status")
async def foundation_status(_: Principal = Depends(require_permission("ung.core.control.read"))):
    return foundation_runtime.health_snapshot()

@router.post("/time-sync/sample")
async def time_sync_sample(body: ClockSampleIn, _: Principal = Depends(require_permission("ung.core.control.write"))):
    sample = ClockSample(source=body.source, source_time_ns=body.source_time_ns, received_monotonic_ns=body.received_monotonic_ns, uncertainty_ns=body.uncertainty_ns)
    status = foundation_runtime.time_sync.update(sample, body.local_wall_time_ns)
    foundation_runtime.observability.gauge("clock_offset_ns", float(status.offset_ns))
    foundation_runtime.observability.gauge("clock_drift_ppm", status.drift_ppm)
    return {"source": status.source, "quality": status.quality.value, "offset_ns": status.offset_ns, "drift_ppm": status.drift_ppm, "uncertainty_ns": status.uncertainty_ns, "age_ms": status.age_ms}

@router.post("/faults")
async def report_fault(body: FaultIn, principal: Principal = Depends(require_permission("ung.core.control.write"))):
    severity_map = {"info": FaultSeverity.INFO, "degraded": FaultSeverity.DEGRADED, "critical": FaultSeverity.CRITICAL}
    severity = severity_map.get(body.severity.lower())
    if severity is None:
        raise HTTPException(400, "severity must be info, degraded, or critical")
    fault = foundation_runtime.faults.report(body.component, body.code, severity, body.message)
    foundation_runtime.hmi.set_system_mode(foundation_runtime.faults.system_mode())
    foundation_runtime.observability.increment("faults_reported")
    await checkpoint_runtime(updated_by=principal.subject)
    return {"component": fault.component, "code": fault.code, "severity": fault.severity.name.lower(), "message": fault.message, "system_mode": foundation_runtime.faults.system_mode()}

@router.delete("/faults/{component}/{code}")
async def clear_fault(component: str, code: str, principal: Principal = Depends(require_permission("ung.core.control.write"))):
    cleared = foundation_runtime.faults.clear(component, code)
    foundation_runtime.hmi.set_system_mode(foundation_runtime.faults.system_mode())
    await checkpoint_runtime(updated_by=principal.subject)
    return {"cleared": cleared, "system_mode": foundation_runtime.faults.system_mode()}

@router.post("/metrics/gauge")
async def set_gauge(body: MetricIn, _: Principal = Depends(require_permission("ung.core.telemetry.write"))):
    foundation_runtime.observability.gauge(body.name, body.value)
    return {"accepted": True}

@router.post("/metrics/counter")
async def increment_counter(body: CounterIn, _: Principal = Depends(require_permission("ung.core.telemetry.write"))):
    foundation_runtime.observability.increment(body.name, body.amount)
    return {"accepted": True}

@router.get("/hmi")
async def hmi_snapshot(_: Principal = Depends(require_permission("ung.core.control.read"))):
    return foundation_runtime.hmi.view()


@router.get("/adapters/{system_key}")
async def foundation_adapter(system_key: str, _: Principal = Depends(require_permission("ung.core.control.read"))):
    return serialize_profile(adapter_profile(system_key))


@router.get("/acceptance")
async def foundation_acceptance(_: Principal = Depends(require_permission("ung.core.control.read"))):
    return foundation_acceptance_report(foundation_runtime)

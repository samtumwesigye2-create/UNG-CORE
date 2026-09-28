import asyncio
import pytest

from app.services.device_identity import DeviceIdentity, DeviceIdentityRegistry, DeviceTrustState
from app.services.event_bus import EventBus
from app.services.mlops_lifecycle import MLOpsLifecycle, ModelRelease, ModelStage
from app.services.resource_scheduler import Priority, ResourceBudget, ResourceScheduler, WorkItem
from app.services.schema_registry import SchemaRegistry
from app.services.sensor_self_test import CheckState, SensorCheck, SensorSelfTestFramework


def test_device_identity_enroll_rotate_and_quarantine():
    reg=DeviceIdentityRegistry()
    reg.enroll(DeviceIdentity("d1","fp1","hw1","1.0","DRACO"))
    reg.set_trust("d1", DeviceTrustState.TRUSTED)
    reg.rotate_certificate("d1","fp2")
    assert reg.get("d1").certificate_fingerprint=="fp2"
    assert reg.set_trust("d1", DeviceTrustState.QUARANTINED).trust_state is DeviceTrustState.QUARANTINED


def test_mlops_staged_promotion():
    life=MLOpsLifecycle()
    life.register(ModelRelease("vision","1","dataset-1","exp-1"))
    life.promote("vision","1",ModelStage.SHADOW)
    life.promote("vision","1",ModelStage.CANARY)
    life.promote("vision","1",ModelStage.PRODUCTION)
    assert life.production("vision").version=="1"


def test_sensor_self_test_fail_closed():
    f=SensorSelfTestFramework()
    f.register_check("imu","whoami",lambda: SensorCheck("whoami",CheckState.PASS))
    f.register_check("imu","data",lambda: (_ for _ in ()).throw(RuntimeError("spi")))
    assert f.run("imu").state is CheckState.FAIL


def test_resource_scheduler_prioritizes_realtime():
    s=ResourceScheduler(ResourceBudget(cpu=4,gpu=1,memory_mb=4096,bandwidth_mbps=100))
    s.submit(WorkItem(Priority.NORMAL,100,"a",ResourceBudget(cpu=1)))
    s.submit(WorkItem(Priority.REALTIME,200,"b",ResourceBudget(cpu=1)))
    assert s.next().work_id=="b"


def test_schema_registry_compatibility():
    r=SchemaRegistry()
    r.register("entity","1","message v1")
    assert r.require_fields_compatible({"id"},{"id","confidence"})


@pytest.mark.asyncio
async def test_event_bus_delivery():
    bus=EventBus()
    q=bus.subscribe("health")
    bus.publish_nowait("health",{"ok":True})
    event=await asyncio.wait_for(q.get(),0.1)
    assert event.payload["ok"] is True

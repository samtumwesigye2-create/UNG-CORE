from app.services.fleet_management import FleetAsset, FleetHealth, FleetManager
from app.services.predictive_maintenance import MaintenanceSignals, PredictiveMaintenance
from app.services.replay_forensics import ReplayRecorder
from app.services.scenario_orchestrator import ScenarioAction, ScenarioOrchestrator, ScenarioStep
from app.services.storage_lifecycle import StorageLifecycleManager, StorageTier
from app.services.verification import check_invariant, verify_transition_graph


def test_replay_hash_chain_and_window():
    r=ReplayRecorder()
    r.append(timestamp_ns=10,stream="imu",payload={"x":1})
    r.append(timestamp_ns=20,stream="camera",payload={"frame":2},model_version="v1")
    assert r.verify()
    assert len(r.between(5,15))==1


def test_scenario_executes_registered_action():
    seen=[]
    s=ScenarioOrchestrator()
    s.register_handler(ScenarioAction.SENSOR_DROPOUT, lambda p: seen.append(p["id"]))
    result=s.execute([ScenarioStep(100,ScenarioAction.SENSOR_DROPOUT,{"id":"cam1"})])
    assert result[0][1]=="executed" and seen==["cam1"]


def test_verification_helpers():
    assert check_invariant("nonnegative",[0,1,2],lambda x:x>=0).passed
    assert verify_transition_graph("machine",{"idle":{"run"},"run":{"idle"}}).passed


def test_storage_retention_and_integrity():
    m=StorageLifecycleManager()
    m.register("a",b"data",StorageTier.HOT,100)
    assert m.verify("a",b"data")
    try:
        m.secure_delete("a",99)
        assert False
    except PermissionError:
        pass
    m.secure_delete("a",100)


def test_fleet_inventory():
    f=FleetManager()
    f.register(FleetAsset("edge1","1","c1","cal1","online",FleetHealth.HEALTHY,deployment_ring="canary"))
    assert len(f.by_ring("canary"))==1
    f.update("edge1", health=FleetHealth.DEGRADED)
    assert len(f.unhealthy())==1


def test_predictive_maintenance_high_risk():
    a=PredictiveMaintenance().assess(MaintenanceSignals(
        vibration_rms=10,battery_soh_percent=20,thermal_cycles=1000,
        fan_rpm_ratio=0,storage_wear_percent=100,sensor_drift_score=1,actuator_error_ratio=1))
    assert a.recommended_action=="service_now"

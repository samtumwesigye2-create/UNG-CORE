from app.services.api_policy import APIPolicyEngine, RequestContext
from app.services.disaster_recovery import BackupState, DisasterRecoveryManager
from app.services.geospatial import Geofence, GeospatialService, MapPoint
from app.services.hmi_state import Alarm, AlarmPriority, HMIState
from app.services.mission_workflow import MissionWorkflowEngine, TaskState, WorkflowTask


def test_dependency_workflow_and_resume():
    w=MissionWorkflowEngine()
    w.add(WorkflowTask("a","mapping"))
    w.add(WorkflowTask("b","inspection",dependencies=("a",),priority=5))
    assert w.refresh_readiness()[0].task_id=="a"
    w.transition("a",TaskState.RUNNING)
    w.transition("a",TaskState.COMPLETED)
    assert w.refresh_readiness()[0].task_id=="b"


def test_geofence_and_route_length():
    g=GeospatialService()
    g.set_map_version("map-1")
    g.add_geofence(Geofence("yard",((0,0),(10,0),(10,10),(0,10))))
    assert g.fences_containing(MapPoint(5,5))==("yard",)
    assert g.route_length_m([MapPoint(0,0),MapPoint(3,4)])==5


def test_hmi_prioritizes_critical_alarm():
    h=HMIState()
    h.raise_alarm(Alarm("a","sensor","warn",AlarmPriority.WARNING))
    h.raise_alarm(Alarm("b","clock","bad",AlarmPriority.CRITICAL))
    assert h.view()["alarms"][0]["alarm_id"]=="b"


def test_api_policy_role_and_rate_limit():
    p=APIPolicyEngine(requests_per_minute=1)
    p.allow_roles("/v1/admin",{"admin"})
    denied=p.evaluate(RequestContext("svc","viewer","/v1/admin",10,"t1"),now=0)
    assert not denied.allowed
    allowed=p.evaluate(RequestContext("svc","admin","/v1/admin",10,"t2"),now=0)
    assert allowed.allowed
    limited=p.evaluate(RequestContext("svc","admin","/v1/admin",10,"t3"),now=1)
    assert limited.reason=="rate_limited"


def test_backup_verify_and_restore_evidence():
    d=DisasterRecoveryManager()
    payload={"config":"v1"}
    d.create("s1",1,payload,rpo_seconds=300,rto_seconds=900)
    assert d.verify("s1",payload).state is BackupState.VERIFIED
    assert d.mark_restore_test("s1",success=True).state is BackupState.RESTORED

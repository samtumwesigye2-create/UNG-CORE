import json, re
from sqlalchemy import select
from app.models.unified_operations import JobRecord, ReportOutput, StorageReference, CompatibilityContract, OperationAudit
from app.services.resource_catalog import get_resource

TERMINAL={"succeeded","failed","cancelled"}; JOB_STATES={"queued","running",*TERMINAL}; REPORT_STATES={"queued","delivered","expired"}; STORAGE_SCHEMES={"postgres","object","archive"}
class OperationConflict(ValueError): pass
class InvalidOperation(ValueError): pass

def _subject(principal): return getattr(principal,"subject",None) or "unknown"
def _permissions(principal): return set(getattr(principal,"permissions",[]) or [])
def authorize_resource_action(principal, resource, action):
    needed=f"ung.core.services.{action}"
    if "ung.core.admin" not in _permissions(principal) and needed not in _permissions(principal): raise PermissionError(needed)
    if not resource.controllable: raise InvalidOperation("resource is not controllable")
    return True

async def upsert_job(db,payload):
    jid=payload.get("job_id"); row=await db.get(JobRecord,jid) if jid else None
    if row is None:
        row=JobRecord(**{k:v for k,v in payload.items() if k in {"job_id","owner","system_key","job_type","state","progress","failure","scheduler_job_id"}}); db.add(row)
    else:
        for k in ("progress","failure","scheduler_job_id"):
            if k in payload: setattr(row,k,payload[k])
    await db.commit(); await db.refresh(row); return row
async def transition_job(db,job_id,state):
    if state not in JOB_STATES: raise InvalidOperation("invalid job state")
    row=await db.get(JobRecord,job_id)
    if not row: return None
    if row.state in TERMINAL and state!=row.state: raise OperationConflict("terminal job cannot transition")
    row.state=state; await db.commit(); await db.refresh(row); return row
async def list_jobs(db): return list((await db.execute(select(JobRecord).order_by(JobRecord.created_at.desc()))).scalars().all())

async def enqueue_output(db,payload):
    row=ReportOutput(**payload); db.add(row); await db.commit(); await db.refresh(row); return row
async def list_outputs(db): return list((await db.execute(select(ReportOutput).order_by(ReportOutput.created_at.desc()))).scalars().all())
async def change_output(db,output_id,state):
    if state not in REPORT_STATES: raise InvalidOperation("invalid output state")
    row=await db.get(ReportOutput,output_id)
    if not row:return None
    if row.state!="queued" and row.state!=state: raise OperationConflict("output is terminal")
    row.state=state; await db.commit(); await db.refresh(row); return row

_SECRET=re.compile(r"(password|passwd|token|secret|apikey|api_key)=",re.I)
async def register_storage_ref(db,payload):
    if payload["scheme"] not in STORAGE_SCHEMES: raise InvalidOperation("unsupported storage scheme")
    if _SECRET.search(payload["reference"]): raise InvalidOperation("storage reference must not contain credentials")
    row=StorageReference(**payload); db.add(row); await db.commit(); await db.refresh(row); return row
async def list_storage_refs(db): return list((await db.execute(select(StorageReference).order_by(StorageReference.logical_name))).scalars().all())
async def resolve_storage_ref(db,logical_name): return (await db.execute(select(StorageReference).where(StorageReference.logical_name==logical_name))).scalar_one_or_none()

def parse_semver(value):
    m=re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)",value)
    if not m: raise InvalidOperation("version must be numeric semantic version x.y.z")
    return tuple(map(int,m.groups()))
def evaluate_transition(current_version,candidate_version,policy):
    cur,new=parse_semver(current_version),parse_semver(candidate_version)
    if policy=="exact": return new==cur
    if policy=="minor-stable": return new[:2]==cur[:2] and new>=cur
    if policy=="major-stable": return new[0]==cur[0] and new>=cur
    raise InvalidOperation("unknown compatibility policy")
async def register_contract(db,payload):
    parse_semver(payload["current_version"]); evaluate_transition(payload["current_version"],payload["current_version"],payload.get("policy","major-stable"))
    row=CompatibilityContract(**payload); db.add(row); await db.commit(); await db.refresh(row); return row
async def list_contracts(db): return list((await db.execute(select(CompatibilityContract).order_by(CompatibilityContract.system_key,CompatibilityContract.component))).scalars().all())

async def request_service_transition(db,principal,resource_id,action):
    if action not in {"start","stop","restart"}: raise InvalidOperation("unsupported service action")
    resource=await get_resource(db,resource_id)
    if resource is None:return None
    authorize_resource_action(principal,resource,action)
    previous=resource.health_state; requested={"start":"running","stop":"stopped","restart":"running"}[action]
    audit=OperationAudit(actor=_subject(principal),action=f"service.{action}",resource_id=resource_id,requested_state=requested,previous_state=previous,resulting_state="requested",success=True,detail="Lifecycle request accepted; execution delegated through service adapter boundary")
    db.add(audit); await db.commit(); await db.refresh(audit)
    return {"resource_id":resource_id,"action":action,"previous_state":previous,"requested_state":requested,"resulting_state":"requested","audit_id":audit.audit_id}

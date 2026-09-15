import json
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.security import current_principal, require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.operator_commands import CommandError, COMMANDS, execute_command
from app.services.unified_operations import *

router=APIRouter(prefix="/v1",tags=["unified-control-plane"])
class JobIn(BaseModel): owner:str; system_key:str; job_type:str; job_id:str|None=None; scheduler_job_id:str|None=None
class StateIn(BaseModel): state:str
class ReportIn(BaseModel): owner:str; system_key:str; report_type:str; storage_ref:str; metadata:dict=Field(default_factory=dict)
class StorageIn(BaseModel): logical_name:str; scheme:str; reference:str; system_key:str; metadata:dict=Field(default_factory=dict)
class ContractIn(BaseModel): system_key:str; component:str; current_version:str; policy:str="major-stable"
class CommandIn(BaseModel): command:str

def err(exc):
    if isinstance(exc,PermissionError): return HTTPException(403,"operation not permitted")
    if isinstance(exc,OperationConflict): return HTTPException(409,str(exc))
    return HTTPException(400,str(exc))

@router.get("/jobs/registry")
async def jobs(db:AsyncSession=Depends(get_db),_:Principal=Depends(require_permission("ung.core.jobs.read"))):
    return [{"job_id":x.job_id,"owner":x.owner,"system_key":x.system_key,"job_type":x.job_type,"state":x.state,"progress":x.progress,"failure":x.failure} for x in await list_jobs(db)]
@router.post("/jobs/registry",status_code=201)
async def job_create(body:JobIn,db:AsyncSession=Depends(get_db),_:Principal=Depends(require_permission("ung.core.jobs.write"))): return await upsert_job(db,body.model_dump(exclude_none=True))
@router.post("/jobs/registry/{job_id}/state")
async def job_state(job_id:str,body:StateIn,db:AsyncSession=Depends(get_db),_:Principal=Depends(require_permission("ung.core.jobs.write"))):
    try:r=await transition_job(db,job_id,body.state)
    except Exception as e: raise err(e)
    if not r: raise HTTPException(404,"job not found")
    return {"job_id":r.job_id,"state":r.state}

@router.get("/reports")
async def reports(db:AsyncSession=Depends(get_db),_:Principal=Depends(require_permission("ung.core.reports.read"))): return [{"output_id":x.output_id,"owner":x.owner,"system_key":x.system_key,"report_type":x.report_type,"state":x.state,"storage_ref":x.storage_ref} for x in await list_outputs(db)]
@router.post("/reports",status_code=201)
async def report_create(body:ReportIn,db:AsyncSession=Depends(get_db),_:Principal=Depends(require_permission("ung.core.reports.write"))):
    p=body.model_dump(); p["metadata_json"]=json.dumps(p.pop("metadata"),sort_keys=True); return await enqueue_output(db,p)
@router.post("/reports/{output_id}/{state}")
async def report_state(output_id:str,state:str,db:AsyncSession=Depends(get_db),_:Principal=Depends(require_permission("ung.core.reports.write"))):
    try:r=await change_output(db,output_id,state)
    except Exception as e: raise err(e)
    if not r: raise HTTPException(404,"output not found")
    return {"output_id":r.output_id,"state":r.state}

@router.get("/storage")
async def storage(db:AsyncSession=Depends(get_db),_:Principal=Depends(require_permission("ung.core.storage.read"))): return [{"storage_id":x.storage_id,"logical_name":x.logical_name,"scheme":x.scheme,"reference":x.reference,"system_key":x.system_key} for x in await list_storage_refs(db)]
@router.post("/storage",status_code=201)
async def storage_create(body:StorageIn,db:AsyncSession=Depends(get_db),_:Principal=Depends(require_permission("ung.core.storage.write"))):
    p=body.model_dump(); p["metadata_json"]=json.dumps(p.pop("metadata"),sort_keys=True)
    try:return await register_storage_ref(db,p)
    except Exception as e: raise err(e)

@router.get("/contracts")
async def contracts(db:AsyncSession=Depends(get_db),_:Principal=Depends(require_permission("ung.core.contracts.read"))): return [{"contract_id":x.contract_id,"system_key":x.system_key,"component":x.component,"current_version":x.current_version,"policy":x.policy,"enabled":x.enabled} for x in await list_contracts(db)]
@router.post("/contracts",status_code=201)
async def contract_create(body:ContractIn,db:AsyncSession=Depends(get_db),_:Principal=Depends(require_permission("ung.core.contracts.write"))):
    try:return await register_contract(db,body.model_dump())
    except Exception as e: raise err(e)

@router.post("/services/{resource_id:path}/{action}")
async def service_action(resource_id:str,action:str,db:AsyncSession=Depends(get_db),principal:Principal=Depends(current_principal)):
    try:r=await request_service_transition(db,principal,resource_id,action)
    except Exception as e: raise err(e)
    if not r: raise HTTPException(404,"resource not found")
    return r

@router.post("/operator/commands")
async def command(body:CommandIn,db:AsyncSession=Depends(get_db),principal:Principal=Depends(current_principal)):
    try:return await execute_command(db,principal,body.command)
    except (CommandError,InvalidOperation,OperationConflict) as e: raise HTTPException(400,str(e))

@router.get("/operator/commands")
async def command_catalog(_:Principal=Depends(current_principal)): return {"commands":[f"UNG {x}" for x in COMMANDS]}

@router.get("/control-plane/summary")
async def control_plane_summary(db:AsyncSession=Depends(get_db),_:Principal=Depends(require_permission("ung.core.control.read"))):
    return {"jobs":len(await list_jobs(db)),"reports":len(await list_outputs(db)),"storage_refs":len(await list_storage_refs(db)),"compatibility_contracts":len(await list_contracts(db)),"command_count":len(COMMANDS)}

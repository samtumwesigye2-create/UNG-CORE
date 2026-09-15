from app.services.resource_catalog import find_resources, get_resource, serialize_resource
from app.services.unified_operations import list_jobs, list_outputs, list_storage_refs, request_service_transition

COMMANDS=("STATUS","JOBS","SERVICES","REPORTS","FIND","SHOW","LOGS","HEALTH","EVENTS","USERS","SESSIONS","STORAGE","DATABASES","QUEUES","CONNECTIONS","START","STOP","RESTART","AUDIT","SIGNOFF")
class CommandError(ValueError): pass

def parse_command(text):
    parts=text.strip().split()
    if parts and parts[0].upper()=="UNG": parts=parts[1:]
    if not parts: raise CommandError("command required")
    command=parts[0].upper()
    if command not in COMMANDS: raise CommandError(f"unknown command: {command}")
    return command,parts[1:]

async def execute_command(db,principal,command_text):
    command,args=parse_command(command_text)
    if command in {"START","STOP","RESTART"}:
        if len(args)!=1: raise CommandError(f"{command} requires one resource id")
        data=await request_service_transition(db,principal,args[0],command.lower())
        if data is None: raise CommandError("resource not found")
    elif command=="JOBS": data=[{"job_id":x.job_id,"system_key":x.system_key,"type":x.job_type,"state":x.state,"progress":x.progress} for x in await list_jobs(db)]
    elif command=="REPORTS": data=[{"output_id":x.output_id,"system_key":x.system_key,"type":x.report_type,"state":x.state,"storage_ref":x.storage_ref} for x in await list_outputs(db)]
    elif command=="STORAGE": data=[{"storage_id":x.storage_id,"logical_name":x.logical_name,"scheme":x.scheme,"system_key":x.system_key} for x in await list_storage_refs(db)]
    elif command=="FIND": data=[serialize_resource(x) for x in await find_resources(db," ".join(args))]
    elif command=="SHOW":
        if len(args)!=1: raise CommandError("SHOW requires one resource id")
        row=await get_resource(db,args[0]); data=serialize_resource(row) if row else None
    elif command in {"SERVICES","DATABASES"}:
        kind="service" if command=="SERVICES" else "database"; data=[serialize_resource(x) for x in await find_resources(db,"",kind)]
    elif command=="SIGNOFF": data={"signoff_url":"/auth/logout","session_action":"terminate-local-session"}
    else: data={"command":command,"status":"available-through-control-plane","arguments":args}
    return {"command":command,"ok":True,"data":data,"error":None}

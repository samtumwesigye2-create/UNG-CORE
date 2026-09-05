from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.core.hardening import production_readiness
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.alerting import alert_summary
from app.services.approvals import approval_summary, assert_gate
from app.services.audit import audit_summary
from app.services.command_history import command_summary
from app.services.control_center import ecosystem_topology
from app.services.control_plane import list_configuration_history, rollback_configuration, serialize_configuration, serialize_configuration_version
from app.services.event_delivery import delivery_summary
from app.services.incident_feed import incident_summary
from app.services.routing import gateway_routing_status
from app.services.scheduler import job_summary
from app.services.security_resilience import resilience_summary
from app.services.telemetry import fleet_health_summary

router = APIRouter(prefix="/v1/control-center", tags=["control-center"])


@router.get("/topology")
async def topology(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.control.read"))):
    return await ecosystem_topology(db)


@router.get("/operations")
async def operations(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.control.read"))):
    return {
        "gateway": await gateway_routing_status(db), "incidents": await incident_summary(db),
        "telemetry": await fleet_health_summary(db), "alerts": await alert_summary(db),
        "audit": await audit_summary(db), "commands": await command_summary(db),
        "approvals": await approval_summary(db), "jobs": await job_summary(db),
        "event_delivery": await delivery_summary(db), "resilience": await resilience_summary(db),
        "readiness": production_readiness(),
    }


@router.get("/readiness")
async def readiness(_: Principal = Depends(require_permission("ung.core.control.read"))):
    return production_readiness()


@router.get("/config/{scope}/{config_key}/history")
async def configuration_history(scope: str, config_key: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.config.read"))):
    rows = await list_configuration_history(db, scope, config_key)
    return [serialize_configuration_version(row) for row in rows]


@router.post("/config/{scope}/{config_key}/rollback/{version}")
async def configuration_rollback(scope: str, config_key: str, version: int, approval_request_id: str | None = None, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission("ung.core.config.write"))):
    gate = await assert_gate(db, action="config.rollback", actor_id=principal.subject, target_type="configuration", target_id=f"{scope}:{config_key}:{version}", context={"scope": scope, "config_key": config_key, "version": version}, approval_request_id=approval_request_id)
    if not gate["allowed"]:
        raise HTTPException(status_code=409, detail={"approval_required": True, "approval_request": gate["request"]})
    try:
        row = await rollback_configuration(db, scope, config_key, version, principal.subject)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="configuration version not found") from exc
    return serialize_configuration(row)


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def control_center_ui():
    return """<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>UNG-CORE Control Center</title><style>:root{font-family:Inter,system-ui,sans-serif;background:#080d19;color:#eef2ff}body{margin:0}.shell{max-width:1240px;margin:auto;padding:24px}.top{display:flex;justify-content:space-between;gap:16px;align-items:center}.brand{font-size:28px;font-weight:850}.sub{color:#98a4bd}.grid{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin:22px 0}.card,.panel{background:#12192a;border:1px solid #27324c;border-radius:15px;padding:16px}.metric{font-size:28px;font-weight:800}.panel{margin-top:12px}.systems{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.system{background:#0c1323;border:1px solid #27324c;border-radius:11px;padding:13px}.badge{display:inline-block;padding:4px 8px;border-radius:999px;background:#27324c;font-size:12px}.toolbar{display:flex;gap:8px;flex-wrap:wrap}input,button{border-radius:9px;border:1px solid #35415e;background:#0c1323;color:#eef2ff;padding:10px 12px}button{cursor:pointer;font-weight:700}@media(max-width:980px){.grid{grid-template-columns:repeat(3,1fr)}}@media(max-width:700px){.systems{grid-template-columns:1fr 1fr}}@media(max-width:520px){.grid,.systems{grid-template-columns:1fr 1fr}.top{align-items:flex-start;flex-direction:column}}</style></head><body><div class='shell'><div class='top'><div><div class='brand'>UNG-CORE Control Center</div><div class='sub'>National control plane · live operations · governance · recovery · production readiness</div></div><div class='toolbar'><input id='token' type='password' placeholder='Bearer token'><button onclick='loadAll()'>Connect</button></div></div><div class='grid'><div class='card'><div class='sub'>Systems</div><div id='total' class='metric'>—</div></div><div class='card'><div class='sub'>Healthy</div><div id='healthy' class='metric'>—</div></div><div class='card'><div class='sub'>Pending Approvals</div><div id='approvals' class='metric'>—</div></div><div class='card'><div class='sub'>Queued Jobs</div><div id='jobs' class='metric'>—</div></div><div class='card'><div class='sub'>Dead Letters</div><div id='dead' class='metric'>—</div></div><div class='card'><div class='sub'>Readiness</div><div id='ready' class='metric'>—</div></div></div><div class='panel'><h3>System Status</h3><div id='systems' class='systems'><span class='sub'>Connect to load status.</span></div></div><div class='panel'><h3>Operations & Recovery</h3><div id='ops' class='sub'>Connect to load state.</div></div><div class='panel'><h3>Ecosystem Topology</h3><div id='topology' class='sub'>Connect to load dependency graph.</div></div></div><script>const headers=()=>({Authorization:'Bearer '+document.getElementById('token').value});async function get(path){const r=await fetch(path,{headers:headers()});if(!r.ok)throw new Error(await r.text());return r.json()}async function loadAll(){try{const [s,t,o]=await Promise.all([get('/v1/control-center/status'),get('/v1/control-center/topology'),get('/v1/control-center/operations')]);total.textContent=s.total_systems;healthy.textContent=o.telemetry.healthy;approvals.textContent=o.approvals.pending;jobs.textContent=o.jobs.queued+o.jobs.scheduled+o.jobs.retry_wait;dead.textContent=o.resilience.dead_letters;ready.textContent=o.readiness.ready?'READY':'BLOCKED';systems.innerHTML=s.systems.map(x=>`<div class='system'><b>${x.display_name}</b><div class='sub'>${x.system_key}</div><p><span class='badge'>${x.status}</span> <span class='badge'>${x.criticality}</span></p></div>`).join('')||'<span class="sub">No systems registered.</span>';ops.innerHTML=`Jobs: <b>${o.jobs.queued}</b> queued · <b>${o.jobs.running}</b> running · <b>${o.jobs.failed}</b> failed<br>Approvals: <b>${o.approvals.pending}</b> pending · Alerts: <b>${o.alerts.active_total}</b> active · Incidents: <b>${o.incidents.open_total}</b> open<br>Events: <b>${o.event_delivery.delivered}</b> delivered · <b>${o.event_delivery.failed}</b> failed<br>Recovery: <b>${o.resilience.dead_letters}</b> dead letters · <b>${o.resilience.circuits.open}</b> open circuits · <b>${o.resilience.active_credentials}</b> credential refs<br>Production checks: <b>${o.readiness.failed_checks}</b> failed`;topology.innerHTML=`<b>${t.node_count}</b> systems · <b>${t.edge_count}</b> dependencies<br><br>`+t.edges.map(e=>`${e.source} → ${e.target} <span class='badge'>${e.type}${e.required?' · required':''}</span>`).join('<br>')}catch(e){alert('Control Center: '+e.message)}}</script></body></html>"""

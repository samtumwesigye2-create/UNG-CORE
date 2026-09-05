from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.security import require_permission
from app.db.session import get_db
from app.schemas.contracts import Principal
from app.services.control_center import ecosystem_topology
from app.services.control_plane import (
    list_configuration_history,
    rollback_configuration,
    serialize_configuration,
    serialize_configuration_version,
)
from app.services.incident_feed import incident_summary
from app.services.routing import gateway_routing_status

router = APIRouter(prefix="/v1/control-center", tags=["control-center"])


@router.get("/topology")
async def topology(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.control.read"))):
    return await ecosystem_topology(db)


@router.get("/operations")
async def operations(db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.control.read"))):
    return {"gateway": await gateway_routing_status(db), "incidents": await incident_summary(db)}


@router.get("/config/{scope}/{config_key}/history")
async def configuration_history(scope: str, config_key: str, db: AsyncSession = Depends(get_db), _: Principal = Depends(require_permission("ung.core.config.read"))):
    rows = await list_configuration_history(db, scope, config_key)
    return [serialize_configuration_version(row) for row in rows]


@router.post("/config/{scope}/{config_key}/rollback/{version}")
async def configuration_rollback(scope: str, config_key: str, version: int, db: AsyncSession = Depends(get_db), principal: Principal = Depends(require_permission("ung.core.config.write"))):
    try:
        row = await rollback_configuration(db, scope, config_key, version, principal.subject)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="configuration version not found") from exc
    return serialize_configuration(row)


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
async def control_center_ui():
    return """<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>UNG-CORE Control Center</title>
<style>
:root{font-family:Inter,system-ui,sans-serif;background:#0b1020;color:#eef2ff}body{margin:0}.shell{max-width:1180px;margin:auto;padding:28px}.top{display:flex;justify-content:space-between;gap:16px;align-items:center}.brand{font-size:28px;font-weight:800}.sub{color:#9aa6c1}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:24px 0}.card,.panel{background:#131a2e;border:1px solid #26304b;border-radius:16px;padding:18px}.metric{font-size:30px;font-weight:800}.panel{margin-top:14px}.systems{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.system{background:#0e1528;border:1px solid #26304b;border-radius:12px;padding:14px}.badge{display:inline-block;padding:4px 9px;border-radius:999px;background:#26304b;font-size:12px}.toolbar{display:flex;gap:8px;flex-wrap:wrap}input,button{border-radius:9px;border:1px solid #34405f;background:#0e1528;color:#eef2ff;padding:10px 12px}button{cursor:pointer;font-weight:700}@media(max-width:800px){.grid,.systems{grid-template-columns:1fr 1fr}}@media(max-width:520px){.grid,.systems{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}}
</style>
</head>
<body><div class='shell'>
<div class='top'><div><div class='brand'>UNG-CORE Control Center</div><div class='sub'>National Grid ecosystem operations, routing and dependency view</div></div><div class='toolbar'><input id='token' type='password' placeholder='Bearer token'><button onclick='loadAll()'>Connect</button></div></div>
<div class='grid'><div class='card'><div class='sub'>Systems</div><div id='total' class='metric'>—</div></div><div class='card'><div class='sub'>Healthy</div><div id='healthy' class='metric'>—</div></div><div class='card'><div class='sub'>Gateway Routes</div><div id='routes' class='metric'>—</div></div><div class='card'><div class='sub'>Open Incidents</div><div id='incidents' class='metric'>—</div></div></div>
<div class='panel'><h3>System Status</h3><div id='systems' class='systems'><span class='sub'>Connect to load status.</span></div></div>
<div class='panel'><h3>Operational State</h3><div id='ops' class='sub'>Connect to load routing and incident state.</div></div>
<div class='panel'><h3>Ecosystem Topology</h3><div id='topology' class='sub'>Connect to load dependency graph.</div></div>
</div>
<script>
const headers=()=>({Authorization:'Bearer '+document.getElementById('token').value});
async function get(path){const r=await fetch(path,{headers:headers()});if(!r.ok)throw new Error(await r.text());return r.json()}
async function loadAll(){try{const [s,t,o]=await Promise.all([get('/v1/control-center/status'),get('/v1/control-center/topology'),get('/v1/control-center/operations')]);
document.getElementById('total').textContent=s.total_systems;document.getElementById('healthy').textContent=s.healthy;document.getElementById('routes').textContent=o.gateway.enabled_routes;document.getElementById('incidents').textContent=o.incidents.open_total;
document.getElementById('systems').innerHTML=s.systems.map(x=>`<div class='system'><b>${x.display_name}</b><div class='sub'>${x.system_key}</div><p><span class='badge'>${x.status}</span> <span class='badge'>${x.criticality}</span></p></div>`).join('')||'<span class="sub">No systems registered.</span>';
document.getElementById('ops').innerHTML=`Gateway: <b>${o.gateway.enabled_routes}</b> enabled / <b>${o.gateway.total_routes}</b> total routes<br>Incidents: <b>${o.incidents.open_total}</b> open · <b>${o.incidents.critical}</b> critical`;
document.getElementById('topology').innerHTML=`<b>${t.node_count}</b> systems · <b>${t.edge_count}</b> dependencies<br><br>`+t.edges.map(e=>`${e.source} → ${e.target} <span class='badge'>${e.type}${e.required?' · required':''}</span>`).join('<br>');}catch(e){alert('Control Center: '+e.message)}}
</script></body></html>"""

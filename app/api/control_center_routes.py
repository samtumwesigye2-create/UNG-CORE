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
    return """<!doctype html>
<html lang='en'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>UNG-CORE Control Center</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;background:#070b14;color:#edf2ff;color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 75% -20%,#182747 0,#070b14 42%);min-height:100vh}a{color:inherit}.app{display:grid;grid-template-columns:240px minmax(0,1fr);min-height:100vh}.side{border-right:1px solid #202b42;background:#0a101d;padding:22px 16px;position:sticky;top:0;height:100vh}.brand{font-weight:900;font-size:21px;letter-spacing:.02em}.brand small{display:block;font-size:11px;color:#7f91b2;letter-spacing:.13em;margin-top:5px}.nav{margin-top:28px;display:grid;gap:6px}.nav a{padding:10px 11px;border-radius:9px;text-decoration:none;color:#9aa8c3;font-weight:650;font-size:14px}.nav a:hover,.nav a.active{background:#131d31;color:#fff}.sidefoot{position:absolute;bottom:22px;left:16px;right:16px}.main{padding:24px 28px 40px;min-width:0}.top{display:flex;align-items:center;justify-content:space-between;gap:16px}.title h1{font-size:27px;margin:0}.sub{color:#8998b5}.tiny{font-size:12px}.toolbar{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.button{border:1px solid #2b3955;background:#10182a;color:#edf2ff;border-radius:9px;padding:9px 12px;text-decoration:none;font-weight:750;font-size:13px;cursor:pointer}.button:hover{background:#18243b}.identity{text-align:right}.identity b{display:block}.metrics{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:11px;margin:22px 0}.card,.panel{background:rgba(15,23,39,.92);border:1px solid #22304a;border-radius:14px}.card{padding:15px}.label{font-size:12px;color:#8696b4;font-weight:700}.metric{font-size:27px;font-weight:900;margin-top:6px}.ok{color:#75dfad}.warn{color:#ffd37a}.bad{color:#ff8a8a}.layout{display:grid;grid-template-columns:minmax(0,1.6fr) minmax(300px,.8fr);gap:12px}.panel{padding:16px;margin-bottom:12px}.panel h2{font-size:16px;margin:0 0 13px}.panelhead{display:flex;justify-content:space-between;align-items:center;gap:10px}.search{width:260px;max-width:48vw;background:#080e19;border:1px solid #2a3853;border-radius:9px;color:#fff;padding:9px 11px}.systems{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.system{background:#0a1120;border:1px solid #25334e;border-radius:11px;padding:13px;min-width:0}.system b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.meta{color:#8392ad;font-size:12px;margin:4px 0 9px}.badges{display:flex;gap:5px;flex-wrap:wrap}.badge{display:inline-block;border:1px solid #31415f;background:#152037;border-radius:999px;padding:3px 7px;font-size:11px;color:#b9c5db}.launch{display:inline-block;margin-top:11px;text-decoration:none;font-size:12px;font-weight:800;color:#9ec5ff}.rows{display:grid;gap:8px}.row{display:flex;justify-content:space-between;gap:10px;padding:10px 0;border-bottom:1px solid #1d2940}.row:last-child{border-bottom:0}.row strong{text-align:right}.sectiongrid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.opbox{border:1px solid #22304a;background:#0a1120;border-radius:11px;padding:12px}.opbox h3{margin:0 0 9px;font-size:13px}.opvalue{font-size:23px;font-weight:900}.hidden{display:none!important}.empty{padding:18px;color:#8594af;text-align:center}.error{border:1px solid #60373d;background:#241316;color:#ffb3b3;border-radius:10px;padding:12px}.topology{font-size:13px;line-height:1.8;max-height:340px;overflow:auto}.mobilebar{display:none}
@media(max-width:1100px){.metrics{grid-template-columns:repeat(3,1fr)}.systems{grid-template-columns:repeat(2,1fr)}}
@media(max-width:820px){.app{display:block}.side{display:none}.main{padding:18px}.mobilebar{display:flex;justify-content:space-between;align-items:center;margin-bottom:18px}.layout{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(3,1fr)}.identity{display:none}}
@media(max-width:560px){.top{align-items:flex-start}.title h1{font-size:23px}.metrics{grid-template-columns:repeat(2,1fr)}.systems,.sectiongrid{grid-template-columns:1fr}.search{width:100%;max-width:none}.panelhead{align-items:flex-start;flex-direction:column}.main{padding:15px}}
</style>
</head>
<body>
<div class='app'>
<aside class='side'>
  <div class='brand'>UNG-CORE<small>NATIONAL CONTROL PLANE</small></div>
  <nav id='nav' class='nav'>
    <a class='active' href='#overview'>Overview</a>
    <a href='#systems'>Systems</a>
    <a data-cap='incidents' href='#operations'>Incidents</a>
    <a data-cap='approvals' href='#operations'>Approvals</a>
    <a data-cap='jobs' href='#operations'>Jobs</a>
    <a data-cap='audit' href='#governance'>Audit & Commands</a>
    <a data-cap='recovery' href='#recovery'>Recovery</a>
  </nav>
  <div class='sidefoot tiny sub'>Independent systems remain standalone.<br>UNG-CORE coordinates through contracts.</div>
</aside>
<main class='main'>
  <div class='mobilebar'><div class='brand'>UNG-CORE</div><a id='mobileLogout' class='button hidden' href='/auth/logout'>Sign out</a></div>
  <div class='top' id='overview'>
    <div class='title'><h1>Control Center</h1><div class='sub'>Live operations · system launch · governance · recovery · readiness</div></div>
    <div class='toolbar'>
      <div id='identity' class='identity hidden'><b id='operatorName'>Operator</b><span id='operatorRoles' class='tiny sub'></span></div>
      <a id='signin' class='button hidden' href='/auth/login'>Sign in with UNG Identity</a>
      <a id='logout' class='button hidden' href='/auth/logout'>Sign out</a>
    </div>
  </div>

  <div class='metrics'>
    <div class='card'><div class='label'>Enabled Systems</div><div id='mSystems' class='metric'>—</div></div>
    <div class='card'><div class='label'>Healthy</div><div id='mHealthy' class='metric'>—</div></div>
    <div class='card'><div class='label'>Active Alerts</div><div id='mAlerts' class='metric'>—</div></div>
    <div class='card'><div class='label'>Pending Approvals</div><div id='mApprovals' class='metric'>—</div></div>
    <div class='card'><div class='label'>Queued Work</div><div id='mJobs' class='metric'>—</div></div>
    <div class='card'><div class='label'>Production</div><div id='mReady' class='metric'>—</div></div>
  </div>

  <div class='layout'>
    <div>
      <section class='panel' id='systems'>
        <div class='panelhead'><h2>Systems & Launchpad</h2><input id='systemSearch' class='search' placeholder='Search system, owner or capability…'></div>
        <div id='systemGrid' class='systems'><div class='empty'>Checking operator session…</div></div>
      </section>

      <section class='panel' id='operations'>
        <div class='panelhead'><h2>Operations</h2><span id='refreshState' class='tiny sub'>Live snapshot</span></div>
        <div id='operationsGrid' class='sectiongrid'><div class='empty'>Loading operational state…</div></div>
      </section>

      <section class='panel' id='governance'>
        <h2>Governance & Delivery</h2>
        <div id='governanceGrid' class='sectiongrid'><div class='empty'>Loading governance state…</div></div>
      </section>
    </div>

    <div>
      <section class='panel'>
        <h2>Production Readiness</h2>
        <div id='readiness' class='rows'><div class='empty'>Loading checks…</div></div>
      </section>
      <section class='panel' id='recovery'>
        <h2>Recovery & Resilience</h2>
        <div id='recoveryState' class='rows'><div class='empty'>Loading recovery state…</div></div>
      </section>
      <section class='panel'>
        <h2>Ecosystem Topology</h2>
        <div id='topologyState' class='topology sub'>Loading dependencies…</div>
      </section>
    </div>
  </div>
</main>
</div>
<script>
const $=id=>document.getElementById(id);
const esc=v=>String(v??'').replace(/[&<>\"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',"'":'&#39;'}[c]));
const num=v=>Number.isFinite(Number(v))?Number(v):0;
let systemsCache=[];
async function get(path){const r=await fetch(path,{credentials:'same-origin'});if(r.status===401)throw new Error('AUTH_REQUIRED');if(r.status===403)throw new Error('FORBIDDEN');if(!r.ok)throw new Error(await r.text());return r.json()}
function box(title,value,detail=''){return `<div class='opbox'><h3>${esc(title)}</h3><div class='opvalue'>${esc(value)}</div><div class='tiny sub'>${esc(detail)}</div></div>`}
function row(label,value,klass=''){return `<div class='row'><span class='sub'>${esc(label)}</span><strong class='${klass}'>${esc(value)}</strong></div>`}
function renderSystems(items){const q=$('systemSearch').value.trim().toLowerCase();const filtered=items.filter(s=>!q||[s.system_key,s.display_name,s.owner_organization_key,...(s.capabilities||[])].join(' ').toLowerCase().includes(q));$('systemGrid').innerHTML=filtered.map(s=>`<div class='system'><b>${esc(s.display_name)}</b><div class='meta'>${esc(s.system_key)} · ${esc(s.owner_organization_key)}</div><div class='badges'><span class='badge'>${esc(s.lifecycle_status)}</span><span class='badge'>${esc(s.criticality)}</span>${(s.capabilities||[]).slice(0,2).map(c=>`<span class='badge'>${esc(c)}</span>`).join('')}</div>${s.launchable?`<a class='launch' href='${esc(s.launch_url)}' target='_blank' rel='noopener noreferrer'>Open system ↗</a>`:`<div class='tiny sub' style='margin-top:11px'>No launch URL registered</div>`}</div>`).join('')||`<div class='empty'>No matching systems.</div>`}
function applyNavigation(nav){document.querySelectorAll('[data-cap]').forEach(a=>{if(!nav[a.dataset.cap])a.classList.add('hidden')})}
function renderDashboard(d,nav){$('mHealthy').textContent=num(d.telemetry?.healthy);$('mAlerts').textContent=num(d.alerts?.active_total);$('mApprovals').textContent=d.approvals?num(d.approvals.pending):'—';$('mJobs').textContent=d.jobs?num(d.jobs.queued)+num(d.jobs.scheduled)+num(d.jobs.retry_wait):'—';$('mReady').textContent=d.readiness?.ready?'READY':'BLOCKED';$('mReady').className='metric '+(d.readiness?.ready?'ok':'bad');
  const ops=[];ops.push(box('Fleet health',`${num(d.telemetry?.healthy)} healthy`,`${num(d.telemetry?.unhealthy)} unhealthy · ${num(d.telemetry?.unknown)} unknown`));ops.push(box('Active alerts',num(d.alerts?.active_total),`${num(d.alerts?.critical)} critical`));if(d.incidents)ops.push(box('Open incidents',num(d.incidents.open_total),`${num(d.incidents.resolved_total)} resolved`));if(d.approvals)ops.push(box('Pending approvals',num(d.approvals.pending),`${num(d.approvals.approved)} approved · ${num(d.approvals.denied)} denied`));if(d.jobs)ops.push(box('Jobs',num(d.jobs.queued)+num(d.jobs.scheduled)+num(d.jobs.retry_wait),`${num(d.jobs.running)} running · ${num(d.jobs.failed)} failed`));$('operationsGrid').innerHTML=ops.join('');
  const gov=[];gov.push(box('Event delivery',num(d.event_delivery?.delivered),`${num(d.event_delivery?.failed)} failed`));if(d.audit)gov.push(box('Audit events',num(d.audit.total),`${num(d.audit.recent_24h)} in last 24h`));if(d.commands)gov.push(box('Commands',num(d.commands.total),`${num(d.commands.failed)} failed`));gov.push(box('Gateway routes',num(d.gateway?.routes_total??d.gateway?.total_routes),`${num(d.gateway?.enabled_routes)} enabled`));$('governanceGrid').innerHTML=gov.join('');
  const checks=d.readiness?.checks||[];$('readiness').innerHTML=checks.map(c=>row(c.key,c.ok?'PASS':'FAIL',c.ok?'ok':'bad')).join('')||row('Overall',d.readiness?.ready?'READY':'BLOCKED',d.readiness?.ready?'ok':'bad');
  if(d.resilience){$('recoveryState').innerHTML=row('Dead letters',num(d.resilience.dead_letters),num(d.resilience.dead_letters)?'warn':'ok')+row('Open circuits',num(d.resilience.circuits?.open),num(d.resilience.circuits?.open)?'bad':'ok')+row('Credential references',num(d.resilience.active_credentials))}else{$('recoveryState').innerHTML=`<div class='empty'>Recovery controls are not available for this role.</div>`;if(!nav.recovery)$('recovery').classList.add('hidden')}
}
function renderTopology(t){$('topologyState').innerHTML=`<b>${num(t.node_count)} systems</b> · <b>${num(t.edge_count)} dependencies</b><br><br>`+(t.edges||[]).map(e=>`${esc(e.source)} → ${esc(e.target)} <span class='badge'>${esc(e.type)}${e.required?' · required':''}</span>`).join('<br>')}
async function loadAll(){try{const [w,d,t]=await Promise.all([get('/v1/operator/workspace'),get('/v1/operator/dashboard'),get('/v1/control-center/topology')]);$('signin').classList.add('hidden');$('logout').classList.remove('hidden');$('mobileLogout').classList.remove('hidden');$('identity').classList.remove('hidden');$('operatorName').textContent=w.operator.display_name||w.operator.subject;$('operatorRoles').textContent=(w.operator.roles||[]).join(' · ')||'UNG operator';$('mSystems').textContent=w.system_count;systemsCache=w.systems||[];applyNavigation(w.navigation||{});renderSystems(systemsCache);renderDashboard(d,w.navigation||{});renderTopology(t);$('refreshState').textContent='Updated now'}catch(e){if(e.message==='AUTH_REQUIRED'){$('signin').classList.remove('hidden');$('logout').classList.add('hidden');$('systemGrid').innerHTML=`<div class='empty'>Sign in with UNG Identity to load the Control Center.</div>`;$('operationsGrid').innerHTML='';$('governanceGrid').innerHTML='';$('readiness').innerHTML='';$('recoveryState').innerHTML='';$('topologyState').textContent='Sign in to load ecosystem topology.'}else{const msg=e.message==='FORBIDDEN'?'Your UNG Identity does not have Control Center access.':e.message;$('systemGrid').innerHTML=`<div class='error'>${esc(msg)}</div>`;$('operationsGrid').innerHTML='';$('refreshState').textContent='Load failed'}}}
$('systemSearch').addEventListener('input',()=>renderSystems(systemsCache));
loadAll();
setInterval(loadAll,30000);
</script>
</body></html>"""

import json, os, sqlite3, zipfile, io, re, secrets
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from slicer import slice_stl
BASE_DIR=Path(__file__).resolve().parent
DB_PATH=Path(os.getenv("UNG_CAD_3D_DB",str(BASE_DIR/"ung_cad_3d.db")))
app=FastAPI(title="UNG-CAD-3D",version="1.2.0")

def now_iso(): return datetime.now(timezone.utc).isoformat()
def get_connection():
    c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c
def init_db():
    c=get_connection()
    c.execute("CREATE TABLE IF NOT EXISTS scenes (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,data_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS print_jobs (id TEXT PRIMARY KEY, printer_id TEXT NOT NULL, machine_file TEXT NOT NULL, status TEXT NOT NULL, created_at TEXT NOT NULL, claimed_at TEXT, completed_at TEXT, result_json TEXT)")
    c.commit(); c.close()
@app.on_event("startup")
def startup(): init_db()

class SceneIn(BaseModel):
    name:str
    data:dict

@app.get("/")
def root(): return RedirectResponse(url="/studio.html")
@app.get("/studio.html")
def studio(): return FileResponse(BASE_DIR/"studio.html")
@app.get("/studio")
def studio_short(): return FileResponse(BASE_DIR/"studio.html")
@app.get("/viewer.html")
def viewer(): return FileResponse(BASE_DIR/"viewer.html")
@app.get("/manufacturing.html")
def manufacturing(): return FileResponse(BASE_DIR/"manufacturing.html")
@app.get("/drafting.html")
def drafting(): return FileResponse(BASE_DIR/"drafting.html")
@app.get("/ung-cad-ad5m-bridge.py")
def bridge(): return FileResponse(BASE_DIR/"ung-cad-ad5m-bridge.py",filename="ung-cad-ad5m-bridge.py")
@app.get("/start-ad5m-bridge.bat")
def bridge_bat(): return FileResponse(BASE_DIR/"start-ad5m-bridge.bat",filename="start-ad5m-bridge.bat")
@app.get("/start-ad5m-bridge.command")
def bridge_mac(): return FileResponse(BASE_DIR/"start-ad5m-bridge.command",filename="start-ad5m-bridge.command",media_type="application/octet-stream")

def printable_entries(names):
    out=[]
    for n in names:
        low=n.lower()
        if low.endswith((".stl",".3mf",".gcode",".gx")) and not low.endswith("draco_gen1_full_assembly_reference.stl"):
            out.append(n)
    return out

@app.post("/api/manufacturing/inspect")
async def inspect(file:UploadFile=File(...)):
    name=file.filename or "project"; data=await file.read(); entries=[]
    if name.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                entries=printable_entries([n for n in z.namelist() if not n.endswith("/")])
        except zipfile.BadZipFile:
            raise HTTPException(400,"Invalid ZIP")
    elif name.lower().endswith((".stl",".3mf",".gcode",".gx")):
        entries=[name]
    else:
        raise HTTPException(400,"Unsupported project type")
    if not entries: raise HTTPException(400,"No printable files found")
    return {"ok":True,"part_count":len(entries),"parts":[Path(n).name for n in entries],
            "printer_profile":"FlashForge Adventurer 5M",
            "assembly_reference_excluded":True}

async def read_selected(file:UploadFile, selected:str):
    data=await file.read()
    if not data: raise HTTPException(400,"Empty package")
    if not selected: raise HTTPException(400,"Select a printable part")
    if file.filename.lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names=printable_entries([n for n in z.namelist() if not n.endswith("/")])
                target=next((n for n in names if Path(n).name==selected or n==selected),None)
                if not target: raise HTTPException(404,"Selected part not found in package")
                return target, z.read(target)
        except zipfile.BadZipFile:
            raise HTTPException(400,"Invalid ZIP")
    if Path(file.filename).name==selected or not selected:
        return file.filename,data
    raise HTTPException(404,"Selected part not found")

@app.post("/api/manufacturing/slice")
async def slice_part(file:UploadFile=File(...), selected:str=Form(...), layer_height:float=Form(0.20)):
    if not (0.08 <= layer_height <= 0.4): raise HTTPException(400,"Layer height must be 0.08–0.40 mm")
    source_name, data=await read_selected(file,selected)
    low=source_name.lower()
    if low.endswith((".gcode",".gx")):
        out=BASE_DIR/"generated"; out.mkdir(exist_ok=True)
        safe=re.sub(r"[^A-Za-z0-9_.-]+","_",Path(source_name).name)
        target=out/safe; target.write_bytes(data)
        return {"ok":True,"status":"machine_file_ready","source":Path(source_name).name,
                "machine_file":target.name,"download":f"/api/manufacturing/download/{target.name}",
                "printer":"FlashForge Adventurer 5M","stats":{"pre_sliced":True},
                "transmission":"local AD5M bridge required"}
    if not low.endswith(".stl"):
        raise HTTPException(400,"This build slices STL; upload pre-sliced G-code/GX directly for transmission")
    try:
        gcode,stats=slice_stl(data,Path(source_name).name,layer_height=layer_height)
    except Exception as e:
        raise HTTPException(422,f"Slicing failed: {e}")
    out=BASE_DIR/"generated"; out.mkdir(exist_ok=True)
    safe=re.sub(r"[^A-Za-z0-9_.-]+","_",Path(source_name).stem)
    target=out/(safe+"_AD5M.gcode")
    target.write_bytes(gcode)
    return {"ok":True,"status":"sliced","source":Path(source_name).name,
            "machine_file":target.name,"download":f"/api/manufacturing/download/{target.name}",
            "printer":"FlashForge Adventurer 5M","stats":stats,
            "transmission":"local AD5M bridge required"}

@app.get("/api/manufacturing/download/{name}")
def download_machine_file(name:str):
    safe=Path(name).name
    target=BASE_DIR/"generated"/safe
    if not target.exists(): raise HTTPException(404,"Machine file not found")
    return FileResponse(target,media_type="application/octet-stream",filename=safe)

class PrintJobIn(BaseModel):
    printer_id:str
    machine_file:str

@app.post("/api/manufacturing/jobs")
def create_print_job(job:PrintJobIn):
    machine=Path(job.machine_file).name
    target=BASE_DIR/"generated"/machine
    if not target.exists(): raise HTTPException(404,"Machine file not found")
    jid=secrets.token_urlsafe(12)
    c=get_connection(); c.execute("INSERT INTO print_jobs (id,printer_id,machine_file,status,created_at) VALUES (?,?,?,?,?)",(jid,job.printer_id.strip(),machine,"queued",now_iso())); c.commit(); c.close()
    return {"ok":True,"job_id":jid,"status":"queued","printer_id":job.printer_id.strip(),"machine_file":machine}

@app.get("/api/manufacturing/jobs/{job_id}")
def get_print_job(job_id:str):
    c=get_connection(); row=c.execute("SELECT * FROM print_jobs WHERE id=?",(job_id,)).fetchone(); c.close()
    if not row: raise HTTPException(404,"Print job not found")
    r=dict(row); r["result"]=json.loads(r.pop("result_json")) if r.get("result_json") else None
    return r

@app.get("/api/bridge/jobs/next")
def bridge_next(printer_id:str):
    c=get_connection(); row=c.execute("SELECT * FROM print_jobs WHERE printer_id=? AND status='queued' ORDER BY created_at LIMIT 1",(printer_id,)).fetchone()
    if not row: c.close(); return {"job":None}
    c.execute("UPDATE print_jobs SET status='claimed',claimed_at=? WHERE id=? AND status='queued'",(now_iso(),row["id"])); c.commit()
    row=c.execute("SELECT * FROM print_jobs WHERE id=?",(row["id"],)).fetchone(); c.close()
    return {"job":{"id":row["id"],"machine_file":row["machine_file"],"download":f"/api/manufacturing/download/{row['machine_file']}"}}

class BridgeResult(BaseModel):
    ok:bool
    result:dict|None=None
    error:str|None=None

@app.post("/api/bridge/jobs/{job_id}/complete")
def bridge_complete(job_id:str, body:BridgeResult):
    c=get_connection(); status="completed" if body.ok else "failed"; result=body.result or {"error":body.error}
    c.execute("UPDATE print_jobs SET status=?,completed_at=?,result_json=? WHERE id=?",(status,now_iso(),json.dumps(result),job_id)); c.commit(); c.close()
    return {"ok":True,"status":status}

@app.get("/api/manufacturing/health")
def manufacturing_health():
    return {"ok":True,"slicer":"OrcaSlicer","printer_profile":"FlashForge Adventurer 5M",
            "direct_railway_printer_connection":False,"local_bridge_required":True}

@app.get("/api/scenes")
def list_scenes():
    c=get_connection(); rows=c.execute("SELECT id,name,created_at,updated_at FROM scenes ORDER BY updated_at DESC").fetchall(); c.close(); return [dict(r) for r in rows]
@app.get("/api/scenes/{scene_id}")
def get_scene(scene_id:int):
    c=get_connection(); row=c.execute("SELECT * FROM scenes WHERE id=?",(scene_id,)).fetchone(); c.close()
    if not row: raise HTTPException(404,"Scene not found")
    r=dict(row); r["data"]=json.loads(r.pop("data_json")); return r
@app.post("/api/scenes")
def create_scene(scene:SceneIn):
    c=get_connection(); n=now_iso(); q=c.execute("INSERT INTO scenes (name,data_json,created_at,updated_at) VALUES (?,?,?,?)",(scene.name,json.dumps(scene.data),n,n)); c.commit(); i=q.lastrowid; c.close(); return {"id":i,"status":"created"}
@app.put("/api/scenes/{scene_id}")
def update_scene(scene_id:int,scene:SceneIn):
    c=get_connection()
    if not c.execute("SELECT id FROM scenes WHERE id=?",(scene_id,)).fetchone():
        c.close(); raise HTTPException(404,"Scene not found")
    c.execute("UPDATE scenes SET name=?,data_json=?,updated_at=? WHERE id=?",(scene.name,json.dumps(scene.data),now_iso(),scene_id)); c.commit(); c.close(); return {"status":"updated"}
@app.delete("/api/scenes/{scene_id}")
def delete_scene(scene_id:int):
    c=get_connection(); c.execute("DELETE FROM scenes WHERE id=?",(scene_id,)); c.commit(); c.close(); return {"status":"deleted"}
@app.get("/health")
def health():
    return {"system":"UNG-CAD-3D","status":"ok","ui":"/studio.html","manufacturing":"/manufacturing.html","ad5m_bridge":"/ung-cad-ad5m-bridge.py"}
app.mount("/static",StaticFiles(directory=BASE_DIR),name="static")

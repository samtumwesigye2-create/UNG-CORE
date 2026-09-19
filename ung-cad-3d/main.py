import json, os, sqlite3, zipfile
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
BASE_DIR=Path(__file__).resolve().parent
DB_PATH=Path(os.getenv("UNG_CAD_3D_DB",str(BASE_DIR/"ung_cad_3d.db")))
app=FastAPI(title="UNG-CAD-3D",version="1.1.0")
def now_iso(): return datetime.now(timezone.utc).isoformat()
def get_connection(): c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row; return c
def init_db():
 c=get_connection(); c.execute("CREATE TABLE IF NOT EXISTS scenes (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,data_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)"); c.commit(); c.close()
@app.on_event("startup")
def startup(): init_db()
class SceneIn(BaseModel): name:str; data:dict
@app.get("/")
def root(): return RedirectResponse(url="/studio.html")
@app.get("/studio.html")
def studio(): return FileResponse(BASE_DIR/"studio.html")
@app.get("/viewer.html")
def viewer(): return FileResponse(BASE_DIR/"viewer.html")
@app.get("/drafting.html")
def drafting(): return FileResponse(BASE_DIR/"drafting.html")
@app.get("/ung-cad-ad5m-bridge.py")
def bridge(): return FileResponse(BASE_DIR/"ung-cad-ad5m-bridge.py",filename="ung-cad-ad5m-bridge.py")
@app.get("/start-ad5m-bridge.bat")
def bridge_bat(): return FileResponse(BASE_DIR/"start-ad5m-bridge.bat",filename="start-ad5m-bridge.bat")
@app.post("/api/manufacturing/inspect")
async def inspect(file:UploadFile=File(...)):
 name=file.filename or "project"; data=await file.read(); parts=[]
 low=name.lower()
 if low.endswith(".zip"):
  import io
  try:
   with zipfile.ZipFile(io.BytesIO(data)) as z: parts=[Path(n).name for n in z.namelist() if n.lower().endswith((".stl",".3mf",".gcode",".gx")) and not n.endswith("/")]
  except zipfile.BadZipFile: raise HTTPException(400,"Invalid ZIP")
 elif low.endswith((".stl",".3mf",".gcode",".gx")): parts=[name]
 else: raise HTTPException(400,"Unsupported project type")
 if not parts: raise HTTPException(400,"No printable geometry or machine file found")
 return {"ok":True,"part_count":len(parts),"parts":parts,"printer_profile":"FlashForge Adventurer 5M"}
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
 if not c.execute("SELECT id FROM scenes WHERE id=?",(scene_id,)).fetchone(): c.close(); raise HTTPException(404,"Scene not found")
 c.execute("UPDATE scenes SET name=?,data_json=?,updated_at=? WHERE id=?",(scene.name,json.dumps(scene.data),now_iso(),scene_id)); c.commit(); c.close(); return {"status":"updated"}
@app.delete("/api/scenes/{scene_id}")
def delete_scene(scene_id:int):
 c=get_connection(); c.execute("DELETE FROM scenes WHERE id=?",(scene_id,)); c.commit(); c.close(); return {"status":"deleted"}
@app.get("/health")
def health(): return {"system":"UNG-CAD-3D","status":"ok","ui":"/studio.html","ad5m_bridge":"/ung-cad-ad5m-bridge.py"}
app.mount("/static",StaticFiles(directory=BASE_DIR),name="static")

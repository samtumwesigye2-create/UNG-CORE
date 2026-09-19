import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("UNG_CAD_3D_DB", str(BASE_DIR / "ung_cad_3d.db")))
app = FastAPI(title="UNG-CAD-3D", version="1.0.0")
def now_iso(): return datetime.now(timezone.utc).isoformat()
def get_connection():
    conn=sqlite3.connect(DB_PATH); conn.row_factory=sqlite3.Row; return conn
def init_db():
    conn=get_connection(); conn.execute("CREATE TABLE IF NOT EXISTS scenes (id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,data_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)"); conn.commit(); conn.close()
@app.on_event("startup")
def startup(): init_db()
class SceneIn(BaseModel):
    name:str
    data:dict
@app.get("/")
def root(): return RedirectResponse(url="/viewer.html")
@app.get("/viewer.html")
def serve_viewer(): return FileResponse(BASE_DIR/"viewer.html")
@app.get("/api/scenes")
def list_scenes():
    conn=get_connection(); rows=conn.execute("SELECT id,name,created_at,updated_at FROM scenes ORDER BY updated_at DESC").fetchall(); conn.close(); return [dict(r) for r in rows]
@app.get("/api/scenes/{scene_id}")
def get_scene(scene_id:int):
    conn=get_connection(); row=conn.execute("SELECT * FROM scenes WHERE id=?",(scene_id,)).fetchone(); conn.close()
    if not row: raise HTTPException(status_code=404, detail="Scene not found")
    result=dict(row); result["data"]=json.loads(result.pop("data_json")); return result
@app.post("/api/scenes")
def create_scene(scene:SceneIn):
    conn=get_connection(); now=now_iso(); cur=conn.execute("INSERT INTO scenes (name,data_json,created_at,updated_at) VALUES (?,?,?,?)",(scene.name,json.dumps(scene.data),now,now)); conn.commit(); sid=cur.lastrowid; conn.close(); return {"id":sid,"status":"created"}
@app.put("/api/scenes/{scene_id}")
def update_scene(scene_id:int, scene:SceneIn):
    conn=get_connection(); existing=conn.execute("SELECT id FROM scenes WHERE id=?",(scene_id,)).fetchone()
    if not existing: conn.close(); raise HTTPException(status_code=404, detail="Scene not found")
    conn.execute("UPDATE scenes SET name=?,data_json=?,updated_at=? WHERE id=?",(scene.name,json.dumps(scene.data),now_iso(),scene_id)); conn.commit(); conn.close(); return {"status":"updated"}
@app.delete("/api/scenes/{scene_id}")
def delete_scene(scene_id:int):
    conn=get_connection(); conn.execute("DELETE FROM scenes WHERE id=?",(scene_id,)); conn.commit(); conn.close(); return {"status":"deleted"}
@app.get("/health")
def health(): return {"system":"UNG-CAD-3D","status":"ok","ui":"/viewer.html"}
app.mount("/static", StaticFiles(directory=BASE_DIR), name="static")

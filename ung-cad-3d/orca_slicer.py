import os, re, shutil, subprocess, tempfile, urllib.request
from pathlib import Path

ORCA_VERSION="2.4.2"
ORCA_URL=f"https://github.com/OrcaSlicer/OrcaSlicer/releases/download/v{ORCA_VERSION}/OrcaSlicer_Linux_AppImage_Ubuntu2404_V{ORCA_VERSION}.AppImage"
CACHE=Path("/tmp/ungcad_orca")
APPIMAGE=CACHE/"OrcaSlicer.AppImage"
APPDIR=CACHE/"squashfs-root"

def _ensure_orca():
    CACHE.mkdir(parents=True,exist_ok=True)
    if not APPIMAGE.exists():
        tmp=APPIMAGE.with_suffix(".download")
        urllib.request.urlretrieve(ORCA_URL,tmp)
        tmp.chmod(0o755)
        tmp.replace(APPIMAGE)
    if not (APPDIR/"AppRun").exists():
        work=CACHE/"extract"
        shutil.rmtree(work,ignore_errors=True); work.mkdir()
        subprocess.run([str(APPIMAGE),"--appimage-extract"],cwd=work,check=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        extracted=work/"squashfs-root"
        if not extracted.exists(): raise RuntimeError("OrcaSlicer extraction failed")
        shutil.rmtree(APPDIR,ignore_errors=True)
        extracted.replace(APPDIR)
        shutil.rmtree(work,ignore_errors=True)
    return APPDIR/"AppRun"

def _profile(*parts):
    p=APPDIR/"resources"/"profiles"/"Flashforge"
    for part in parts: p=p/part
    if not p.exists(): raise RuntimeError(f"Missing Orca profile: {p.name}")
    return p

def _validate_gcode(data: bytes):
    text=data.decode("utf-8","ignore")
    move_count=len(re.findall(r"(?m)^G[01]\\s",text))
    extrusion_count=len(re.findall(r"(?m)^G1\\s+[^;\\n]*\\bE-?\\d",text))
    layer_count=max(len(re.findall(r"(?mi)^;LAYER",text)),len(re.findall(r"(?mi)^; CHANGE_LAYER",text)))
    if move_count < 100 or extrusion_count < 50:
        raise RuntimeError(f"Generated machine file failed validation (moves={move_count}, extrusion_moves={extrusion_count})")
    return {"moves":move_count,"extrusion_moves":extrusion_count,"layers_detected":layer_count}

def slice_stl_orca(data: bytes, filename: str, layer_height=0.20):
    app=_ensure_orca()
    machine=_profile("machine","Flashforge Adventurer 5M 0.4 Nozzle.json")
    process=_profile("process","0.20mm Standard @Flashforge AD5M 0.4 Nozzle.json")
    fixed_machine=CACHE/"ungcad-ad5m-machine.json"
    import json
    mcfg=json.loads(machine.read_text())
    mcfg["use_relative_e_distances"]="0"
    mcfg["layer_change_gcode"]="G92 E0"
    fixed_machine.write_text(json.dumps(mcfg))
    filament=_profile("filament","Flashforge PLA Basic.json")
    with tempfile.TemporaryDirectory(prefix="ungcad_orca_job_") as td:
        td=Path(td); src=td/(re.sub(r"[^A-Za-z0-9_.-]+","_",Path(filename).stem)+".stl")
        out=td/"out"; out.mkdir(); src.write_bytes(data)
        cmd=[str(app),str(src),"--load-settings",f"{fixed_machine};{process}","--load-filaments",str(filament),
             "--arrange","1","--slice","0","--outputdir",str(out)]
        env=os.environ.copy(); env.setdefault("QT_QPA_PLATFORM","offscreen")
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,env=env,timeout=300)
        if p.returncode != 0:
            raise RuntimeError("OrcaSlicer failed: "+p.stdout[-1200:])
        files=sorted(out.glob("*.gcode"))
        if not files:
            files=sorted(td.glob("*.gcode"))
        if not files:
            raise RuntimeError("OrcaSlicer completed without producing G-code")
        payload=files[0].read_bytes()
        stats=_validate_gcode(payload)
        stats.update({"engine":"OrcaSlicer","engine_version":ORCA_VERSION,"printer_profile":"Flashforge Adventurer 5M 0.4 Nozzle","process_profile":"0.20mm Standard","filament_profile":"Flashforge PLA Basic","bytes":len(payload)})
        return payload,stats

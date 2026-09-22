import asyncio, json, os, tempfile, time, urllib.request, urllib.parse
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse
from flashforge import FlashForgeClient, FiveMClientConnectionOptions, PrinterDiscovery

HOST="127.0.0.1"; PORT=8765
CLOUD=os.getenv("UNG_CAD_CLOUD","https://ung-cad-3d-production.up.railway.app").rstrip("/")
PRINTER_ID=os.getenv("UNG_CAD_PRINTER_ID","SNMTUF9100669")
BRIDGE_VERSION="2026-09-21-4"
STATE={"printer":None,"check_code":None}

async def discover():
    found=await PrinterDiscovery().discover()
    return [{"name":p.name,"ip":p.ip_address,"serial":p.serial_number,"http_port":p.event_port,"tcp_port":p.command_port} for p in found if p.serial_number]

async def connect(check_code):
    found=await PrinterDiscovery().discover()
    if not found: raise RuntimeError("No FlashForge printer discovered on this LAN")
    p=next((x for x in found if x.serial_number),None)
    if not p: raise RuntimeError("Discovered printer did not report a serial number")
    opts=FiveMClientConnectionOptions(http_port=p.event_port,tcp_port=p.command_port)
    async with FlashForgeClient(p.ip_address,p.serial_number,check_code,options=opts) as c:
        try:
            info=await c.get_printer_status()
        except Exception as e:
            msg=str(e)
            if "Access code is different" in msg or "access code is different" in msg:
                raise RuntimeError("Access Code mismatch — enter the CURRENT Access Code / Check Code shown in the printer Network settings")
            raise
        if not info: raise RuntimeError("Printer rejected connection / Access Code")
        STATE["printer"]={"name":c.printer_name or p.name,"ip":p.ip_address,"serial":p.serial_number,"firmware":c.firmware_version,"http_port":p.event_port,"tcp_port":p.command_port}
        STATE["check_code"]=check_code
        return STATE["printer"]

async def print_file(path, level=True):
    if not STATE["check_code"]: raise RuntimeError("Pair printer first")
    found=await PrinterDiscovery().discover()
    serial=STATE["printer"]["serial"]
    p=next((x for x in found if x.serial_number==serial),None)
    if not p: raise RuntimeError("Paired printer is not discoverable")
    opts=FiveMClientConnectionOptions(http_port=p.event_port,tcp_port=p.command_port)
    async with FlashForgeClient(p.ip_address,p.serial_number,STATE["check_code"],options=opts) as c:
        info=await c.get_printer_status()
        if not info: raise RuntimeError("Printer connection failed")
        await c.init_control()
        uploaded=await c.job_control.upload_file(path,start_print=False,level_before_print=level)
        if not uploaded: raise RuntimeError("Printer rejected file upload")
        started=await c.job_control.print_local_file(Path(path).name,leveling_before_print=level)
        if not started: raise RuntimeError("File uploaded but printer rejected explicit start command")
        await asyncio.sleep(2)
        verify=await c.get_printer_status()
        state=str(getattr(verify,"machine_state","unknown"))
        if "READY" in state.upper() or "IDLE" in state.upper():
            raise RuntimeError("Printer accepted the command but remained idle; print did not start")
        return {"started":True,"file":Path(path).name,"mode":"upload_then_explicit_start","printer_state":state}


def cloud_json(path, method="GET", body=None):
    data=None if body is None else json.dumps(body).encode()
    req=urllib.request.Request(CLOUD+path,data=data,method=method,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=30) as r: return json.loads(r.read() or b"{}")

def cloud_worker():
    while True:
        try:
            q=urllib.parse.urlencode({"printer_id":PRINTER_ID})
            j=cloud_json("/api/bridge/jobs/next?"+q).get("job")
            if j:
                fd,path=tempfile.mkstemp(prefix="ungcad_cloud_",suffix=Path(j["machine_file"]).suffix); os.close(fd)
                try:
                    urllib.request.urlretrieve(CLOUD+j["download"],path)
                    result=asyncio.run(print_file(path,True))
                    cloud_json("/api/bridge/jobs/"+j["id"]+"/complete","POST",{"ok":True,"result":result})
                except Exception as e:
                    cloud_json("/api/bridge/jobs/"+j["id"]+"/complete","POST",{"ok":False,"error":str(e)})
                finally:
                    try: os.unlink(path)
                    except: pass
        except Exception as e:
            print("Cloud queue:",e)
        time.sleep(3)

class H(BaseHTTPRequestHandler):
    def cors(self,code=200,ctype="application/json"):
        self.send_response(code); self.send_header("Content-Type",ctype); self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Access-Control-Allow-Headers","Content-Type,X-Printer-ID,X-Filename,X-Level"); self.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS"); self.end_headers()
    def do_OPTIONS(self): self.cors(204)
    def out(self,obj,code=200): self.cors(code); self.wfile.write(json.dumps(obj).encode())
    def do_GET(self):
        try:
            if self.path=="/health": return self.out({"ok":True,"bridge":"UNG-CAD AD5M","version":BRIDGE_VERSION,"printer":STATE["printer"]})
            if self.path=="/discover": return self.out({"printers":asyncio.run(discover())})
            return self.out({"error":"not found"},404)
        except Exception as e: self.out({"error":str(e)},500)
    def do_POST(self):
        try:
            if self.path=="/pair":
                n=int(self.headers.get("Content-Length","0")); data=json.loads(self.rfile.read(n) or b"{}")
                code=str(data.get("printer_id","")).strip()
                if not code: return self.out({"error":"Printer ID required"},400)
                return self.out({"paired":True,"printer":asyncio.run(connect(code))})
            if self.path=="/print":
                name=self.headers.get("X-Filename","print.gcode")
                if not name.lower().endswith((".gcode",".gx",".3mf")): return self.out({"error":"File must already be sliced (.gcode/.gx/.3mf)"},400)
                n=int(self.headers.get("Content-Length","0")); raw=self.rfile.read(n)
                safe_name=Path(name).name
                tmpdir=tempfile.mkdtemp(prefix="ungcad_")
                path=str(Path(tmpdir)/safe_name); Path(path).write_bytes(raw)
                try: return self.out(asyncio.run(print_file(path,self.headers.get("X-Level","true").lower()=="true")))
                finally:
                    try:
                        os.unlink(path); os.rmdir(tmpdir)
                    except: pass
            return self.out({"error":"not found"},404)
        except Exception as e: self.out({"error":str(e)},500)
    def log_message(self,*args): pass

if __name__=="__main__":
    import threading
    print(f"UNG-CAD AD5M bridge ready on http://{HOST}:{PORT}; cloud queue {CLOUD}")
    threading.Thread(target=cloud_worker,daemon=True).start()
    ThreadingHTTPServer((HOST,PORT),H).serve_forever()

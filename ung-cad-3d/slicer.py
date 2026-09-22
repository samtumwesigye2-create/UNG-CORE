import io, math, tempfile
from pathlib import Path
import numpy as np
import trimesh
from shapely.geometry import Polygon, MultiPolygon

def _loop_points(coords, z):
    pts=[]
    for p in coords:
        pts.append((float(p[0]), float(p[1]), z))
    if len(pts)>1 and pts[0] == pts[-1]:
        pts.pop()
    return pts

def _emit_loop(lines, pts, xoff, yoff, z, e_state, feed=1800):
    if len(pts)<3: return e_state
    px,py,_=pts[0]
    lines.append(f"G0 X{px+xoff:.3f} Y{py+yoff:.3f}")
    for x,y,_ in pts[1:]+[pts[0]]:
        dist=math.hypot(x-px,y-py)
        e_state += dist*0.045
        lines.append(f"G1 X{x+xoff:.3f} Y{y+yoff:.3f} E{e_state:.5f} F{feed}")
        px,py=x,y
    return e_state

def _wall_polygons(poly: Polygon, nozzle: float, wall_count: int):
    """Yield one inset Polygon per perimeter wall, outermost first.
    Wall i sits nozzle*(i+0.5) mm inside the original boundary, which is
    the standard centerline offset for a nozzle of that width. Stops early
    if a requested wall would collapse the shape (too thin to fit)."""
    shells=[]
    for i in range(max(1,wall_count)):
        inset=nozzle*(i+0.5)
        shrunk=poly.buffer(-inset, join_style=2)
        if shrunk.is_empty:
            break
        shells.append(shrunk)
    return shells

def _emit_wall_shell(lines, shell, xoff, yoff, z, e_state):
    geoms=shell.geoms if isinstance(shell,MultiPolygon) else [shell]
    for g in geoms:
        if g.is_empty or not isinstance(g,Polygon): continue
        e_state=_emit_loop(lines,_loop_points(np.asarray(g.exterior.coords),z),xoff,yoff,z,e_state)
        for ring in g.interiors:
            e_state=_emit_loop(lines,_loop_points(np.asarray(ring.coords),z),xoff,yoff,z,e_state)
    return e_state

def slice_stl(data: bytes, filename: str, layer_height=0.20, nozzle=0.40, wall_count=2, bed=220):
    mesh=trimesh.load_mesh(io.BytesIO(data), file_type='stl')
    if not isinstance(mesh,trimesh.Trimesh):
        raise ValueError("STL did not produce a mesh")
    repaired=False
    if not mesh.is_watertight:
        repaired=True
        mesh.remove_unreferenced_vertices()
        mesh.merge_vertices()
        trimesh.repair.fix_normals(mesh, multibody=True)
        trimesh.repair.fix_winding(mesh)
        trimesh.repair.fill_holes(mesh)
        mesh.remove_unreferenced_vertices()
        mesh.merge_vertices()
    open_shell = not mesh.is_watertight
    ext=mesh.extents
    if max(ext[:2]) > bed-10:
        raise ValueError(f"Model XY footprint {max(ext[:2]):.1f} mm exceeds Adventurer 5M 220 mm bed")
    zmin,zmax=mesh.bounds[:,2]
    if zmax-zmin <= 0:
        raise ValueError("Model has zero height")
    xmin,ymin=mesh.bounds[0][:2]; xmax,ymax=mesh.bounds[1][:2]
    xoff=(bed-(xmin+xmax))/2
    yoff=(bed-(ymin+ymax))/2
    first=layer_height/2
    heights=np.arange(first, float(zmax-zmin)+1e-6, layer_height)
    paths=mesh.section_multiplane(plane_origin=[0,0,zmin], plane_normal=[0,0,1], heights=heights)
    lines=[
        "; UNG-CAD generated G-code",
        f"; Model: {filename}",
        "; Printer: FlashForge Adventurer 5M",
        f"; Profile: {nozzle}mm nozzle / {layer_height}mm layers / {wall_count} walls / PLA",
        "; NOTE: verify material, bed/nozzle temperature and first layer before production use",
        "G90","M82","M107","G28",
        "M140 S55","M104 S200","M190 S55","M109 S200",
        "G92 E0","G1 Z0.20 F600","G1 X10 Y10 F6000",
        "G1 Z0.20 F600"
    ]
    e=0.0
    layer_count=0
    for z,path in zip(heights,paths):
        if path is None or len(path.entities)==0: continue
        polys=path.polygons_full
        if not polys: continue
        layer_count+=1
        lines.append(f";LAYER:{layer_count}")
        lines.append(f"G1 Z{z:.3f} F600")
        for poly in polys:
            if not poly.is_valid or poly.area<=0: continue
            for shell in _wall_polygons(poly, nozzle, wall_count):
                e=_emit_wall_shell(lines, shell, xoff, yoff, z, e)
    lines += [
        "G1 E-1.0000 F1800","G1 Z5.000 F600","G1 X0 Y110 F6000",
        "M104 S0","M140 S0","M107","M84",";END"
    ]
    if layer_count==0:
        raise ValueError("No printable cross-sections were generated")
    payload=("\n".join(lines)+"\n").encode()
    return payload, {"layers":layer_count,"height_mm":round(float(zmax-zmin),2),
                     "size_xy_mm":[round(float(ext[0]),2),round(float(ext[1]),2)],
                     "wall_count":wall_count,"bytes":len(payload),
                     "mesh_repaired":repaired,"open_shell_sliced":open_shell}

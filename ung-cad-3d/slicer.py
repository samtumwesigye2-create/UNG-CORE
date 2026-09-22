import io, math
import numpy as np
import trimesh
from shapely.geometry import Polygon, MultiPolygon, LineString
from shapely.ops import unary_union

MATERIALS={
 "PLA":{"nozzle":200,"bed":55,"fan":255,"flow":1.0},
 "PETG":{"nozzle":240,"bed":75,"fan":128,"flow":1.0},
}
QUALITY={
 "quality":{"layer":0.16,"walls":3,"infill":0.18,"speed":1800},
 "balanced":{"layer":0.20,"walls":2,"infill":0.15,"speed":2400},
 "fast":{"layer":0.28,"walls":2,"infill":0.12,"speed":3600},
}

def _polys(g):
    if g is None or g.is_empty:return []
    if isinstance(g,Polygon):return [g]
    if isinstance(g,MultiPolygon):return list(g.geoms)
    return [x for x in getattr(g,"geoms",[]) if isinstance(x,Polygon)]

def _loop(coords,z):
    p=[(float(x),float(y),z) for x,y,*_ in coords]
    if len(p)>1 and p[0]==p[-1]:p.pop()
    return p

def _e_per_mm(layer,line,filament=1.75,flow=1.0):
    return (layer*line)/(math.pi*(filament/2)**2)*flow

def _move(lines,state,x,y,z,e_per,feed,extrude=True,first=False):
    px,py=state["xy"]; d=math.hypot(x-px,y-py)
    if not extrude:
        if state["extruding"]:
            state["e"]-=0.8; lines.append(f"G1 E{state['e']:.5f} F1800")
            if not first: lines.append(f"G1 Z{z+0.2:.3f} F900")
        lines.append(f"G0 X{x:.3f} Y{y:.3f} F{min(feed*2,9000):.0f}")
        if state["extruding"]:
            if not first: lines.append(f"G1 Z{z:.3f} F900")
            state["e"]+=0.8; lines.append(f"G1 E{state['e']:.5f} F1800")
        state["extruding"]=False
    else:
        state["e"]+=d*e_per; lines.append(f"G1 X{x:.3f} Y{y:.3f} E{state['e']:.5f} F{feed:.0f}"); state["extruding"]=True
    state["xy"]=(x,y)

def _emit_ring(lines,state,coords,xoff,yoff,z,e_per,feed,first=False):
    pts=_loop(coords,z)
    if len(pts)<3:return
    x,y,_=pts[0]; _move(lines,state,x+xoff,y+yoff,z,e_per,feed,False,first)
    for x,y,_ in pts[1:]+[pts[:1][0]]:
        _move(lines,state,x+xoff,y+yoff,z,e_per,feed,True,first)

def _emit_geom(lines,state,g,xoff,yoff,z,e_per,feed,first=False):
    for p in _polys(g):
        _emit_ring(lines,state,p.exterior.coords,xoff,yoff,z,e_per,feed,first)
        for r in p.interiors:_emit_ring(lines,state,r.coords,xoff,yoff,z,e_per,feed,first)

def _infill_lines(region,spacing,angle=0):
    if region.is_empty:return []
    minx,miny,maxx,maxy=region.bounds; diag=math.hypot(maxx-minx,maxy-miny)+20
    lines=[]
    if angle%180==0:
        y=miny-spacing
        while y<=maxy+spacing: lines.append(LineString([(minx-diag,y),(maxx+diag,y)])); y+=spacing
    else:
        x=minx-spacing
        while x<=maxx+spacing: lines.append(LineString([(x,miny-diag),(x,maxy+diag)])); x+=spacing
    out=[]
    for l in lines:
        cut=region.intersection(l)
        for g in getattr(cut,"geoms",[cut]):
            if isinstance(g,LineString) and g.length>0.5:out.append(g)
    return out

def _emit_lines(lines,state,paths,xoff,yoff,z,e_per,feed,first=False):
    for p in paths:
        c=list(p.coords)
        if len(c)<2:continue
        x,y=c[0]; _move(lines,state,x+xoff,y+yoff,z,e_per,feed,False,first)
        for x,y in c[1:]:_move(lines,state,x+xoff,y+yoff,z,e_per,feed,True,first)

def _repair(mesh):
    repaired=False
    if not mesh.is_watertight:
        repaired=True; mesh.remove_unreferenced_vertices(); mesh.merge_vertices()
        trimesh.repair.fix_normals(mesh,multibody=True); trimesh.repair.fix_winding(mesh); trimesh.repair.fill_holes(mesh)
        mesh.remove_unreferenced_vertices(); mesh.merge_vertices()
    return repaired

def _auto_orient(mesh):
    # Safe automatic orientation: place the largest axis-aligned face footprint on XY.
    ext=np.array(mesh.extents); best=int(np.argmin(ext))
    if best==0: mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2,[0,1,0]))
    elif best==1: mesh.apply_transform(trimesh.transformations.rotation_matrix(math.pi/2,[1,0,0]))
    mesh.apply_translation([0,0,-mesh.bounds[0,2]])
    return mesh

def slice_stl(data:bytes,filename:str,layer_height=0.20,nozzle=0.40,wall_count=2,bed=220,
              quality="balanced",material="PLA",supports="auto",copies=1,infill=None):
    mesh=trimesh.load_mesh(io.BytesIO(data),file_type="stl")
    if not isinstance(mesh,trimesh.Trimesh):raise ValueError("STL did not produce a mesh")
    repaired=_repair(mesh); mesh=_auto_orient(mesh); ext=mesh.extents
    if max(ext[:2])>bed-10 or ext[2]>220:raise ValueError("Model exceeds Adventurer 5M build volume")
    q=QUALITY.get(quality,QUALITY["balanced"]); mat=MATERIALS.get(material.upper(),MATERIALS["PLA"])
    layer_height=float(layer_height or q["layer"]); wall_count=max(1,int(wall_count or q["walls"])); density=float(q["infill"] if infill is None else infill)
    xmin,ymin=mesh.bounds[0][:2]; xmax,ymax=mesh.bounds[1][:2]; xoff=(bed-(xmin+xmax))/2; yoff=(bed-(ymin+ymax))/2
    heights=np.arange(layer_height/2,float(ext[2])+1e-6,layer_height)
    sections=mesh.section_multiplane([0,0,0],[0,0,1],heights=heights)
    regions=[]
    for path in sections:
        try: regions.append(unary_union([p for p in path.polygons_full if p.is_valid and p.area>0]) if path is not None else Polygon())
        except Exception: regions.append(Polygon())
    if not any(not r.is_empty for r in regions):raise ValueError("No printable cross-sections were generated")
    line_width=nozzle*1.05; eper=_e_per_mm(layer_height,line_width,flow=mat["flow"])
    first_feed=900; wall_feed=q["speed"]; infill_feed=min(q["speed"]*1.25,4800)
    lines=["; UNG-CAD Native Slicer 2",f"; Model: {filename}",f"; Quality: {quality}; Material: {material}; Infill: {density:.0%}",
           "G90","M82","M107","G28",f"M140 S{mat['bed']}",f"M104 S{mat['nozzle']}",f"M190 S{mat['bed']}",f"M109 S{mat['nozzle']}",
           "G92 E0","G1 Z0.28 F600","G1 X10 Y10 F6000","G1 X80 Y10 E8 F600","G92 E0"]
    state={"e":0.0,"xy":(80.0,10.0),"extruding":False}; total_len=0.0; support_layers=0
    top_bottom=max(3,int(round(0.8/layer_height)))
    for i,(z,region) in enumerate(zip(heights,regions)):
        if region.is_empty:continue
        first=i==0; lines += [f";LAYER:{i+1}",f"G1 Z{z:.3f} F600"]
        if i==1: lines.append(f"M106 S{mat['fan']}")
        # brim for small bed contact
        if first and region.area<1200:
            for k in range(4,0,-1):_emit_geom(lines,state,region.buffer(k*line_width),xoff,yoff,z,eper,first_feed,True)
        # perimeter walls
        for w in range(wall_count):
            shell=region.buffer(-line_width*(w+0.5),join_style=2)
            _emit_geom(lines,state,shell,xoff,yoff,z,eper,first_feed if first else wall_feed,first)
        inner=region.buffer(-line_width*(wall_count+0.5))
        # solid top/bottom; otherwise alternating grid/line infill
        above=regions[i+1] if i+1<len(regions) else Polygon(); below=regions[i-1] if i else Polygon()
        exposed_top=region.difference(above.buffer(line_width)) if i+1<len(regions) else region
        exposed_bottom=region.difference(below.buffer(line_width)) if i else region
        solid=(i<top_bottom or i>=len(regions)-top_bottom or exposed_top.area>1 or exposed_bottom.area>1)
        spacing=line_width if solid else max(line_width*2,line_width/max(density,0.05))
        _emit_lines(lines,state,_infill_lines(inner,spacing,0 if i%2==0 else 90),xoff,yoff,z,eper,first_feed if first else infill_feed,first)
        # conservative support detection: unsupported area relative to previous layer, emitted as sparse support
        if supports=="auto" and i>0 and not below.is_empty:
            unsupported=region.difference(below.buffer(line_width*1.5)).buffer(-line_width)
            if not unsupported.is_empty and unsupported.area>4:
                support_layers+=1
                _emit_lines(lines,state,_infill_lines(unsupported,max(line_width*5,2.0),90 if i%2 else 0),xoff,yoff,z,eper,wall_feed,False)
    lines += ["G1 E-0.8000 F1800","G1 Z5 F900","G1 X0 Y110 F6000","M104 S0","M140 S0","M107","M84",";END"]
    payload=("\n".join(lines)+"\n").encode()
    moves=sum(1 for x in lines if x.startswith(("G0 ","G1 "))); extr=sum(1 for x in lines if x.startswith("G1 ") and " E" in x)
    if moves<50 or extr<20:raise ValueError("Generated machine file failed pre-print validation")
    # Estimate from emitted E and profile speed; intentionally approximate.
    filament_m=max(state["e"],0)/1000; grams=filament_m*(math.pi*(1.75/2)**2)*1.24
    estimate_min=max(1,int(moves*0.045))
    return payload,{"layers":len(regions),"height_mm":round(float(ext[2]),2),"size_xy_mm":[round(float(ext[0]),2),round(float(ext[1]),2)],
      "wall_count":wall_count,"infill_percent":round(density*100),"top_bottom_layers":top_bottom,"support_layers":support_layers,
      "material":material.upper(),"quality":quality,"filament_m":round(filament_m,2),"material_g":round(grams,1),"estimated_minutes":estimate_min,
      "bytes":len(payload),"moves":moves,"extrusion_moves":extr,"mesh_repaired":repaired,"open_shell_sliced":not mesh.is_watertight,
      "auto_oriented":True,"brim_auto":regions[0].area<1200 if regions else False,"validation":"passed"}

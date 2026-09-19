import * as THREE from 'three';
import { OrbitControls } from 'https://cdn.jsdelivr.net/npm/three@0.140.0/examples/jsm/controls/OrbitControls.js';
const previewEl=document.getElementById('preview3d'),placeholder=document.getElementById('previewPlaceholder'),previewStats=document.getElementById('previewStats');
const scene=new THREE.Scene();scene.background=new THREE.Color(0x0f1b4d);
const camera=new THREE.PerspectiveCamera(50,1,.1,4000);
const renderer=new THREE.WebGLRenderer({antialias:true});
previewEl.appendChild(renderer.domElement);
const controls=new OrbitControls(camera,renderer.domElement);
scene.add(new THREE.AmbientLight(0xffffff,.7));
const dl=new THREE.DirectionalLight(0xffffff,.9);dl.position.set(150,200,150);scene.add(dl);
scene.add(new THREE.GridHelper(250,25,0x475569,0x1e293b));
scene.add(new THREE.AxesHelper(40));
let mesh=null;
function resize(){const w=previewEl.clientWidth,h=previewEl.clientHeight||320;camera.aspect=w/h;camera.updateProjectionMatrix();renderer.setSize(w,h);}
window.addEventListener('resize',resize);
(function frame(){requestAnimationFrame(frame);controls.update();renderer.render(scene,camera);})();
function meshFromPolys(polys){const pos=[],nor=[];for(const p of polys)for(let k=1;k<p.vertices.length-1;k++)for(const v of[p.vertices[0],p.vertices[k],p.vertices[k+1]]){pos.push(v.pos.x,v.pos.y,v.pos.z);nor.push(v.normal.x,v.normal.y,v.normal.z);}const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));g.setAttribute('normal',new THREE.Float32BufferAttribute(nor,3));return new THREE.Mesh(g,new THREE.MeshStandardMaterial({color:0x3b82f6,side:THREE.DoubleSide}));}
function computeVolume(polys){let vol=0;for(const p of polys)for(let k=1;k<p.vertices.length-1;k++){const a=p.vertices[0].pos,b=p.vertices[k].pos,c=p.vertices[k+1].pos;vol+=(a.x*(b.y*c.z-b.z*c.y)-a.y*(b.x*c.z-b.z*c.x)+a.z*(b.x*c.y-b.y*c.x))/6;}return Math.abs(vol);}
window.__previewSTL=function(label,arrayBuffer){
  try{
    const polys=window.CSGEngine.parseSTL(arrayBuffer);
    if(!polys.length){previewStats.textContent='Could not read geometry from '+label;return;}
    placeholder.style.display='none';
    if(mesh)scene.remove(mesh);
    mesh=meshFromPolys(polys);
    scene.add(mesh);
    const bb=window.CSGEngine.boundingBox(polys);
    const size={x:bb.max.x-bb.min.x,y:bb.max.y-bb.min.y,z:bb.max.z-bb.min.z};
    const vol=computeVolume(polys);
    const fits=Math.max(size.x,size.y)<=210&&size.z<=220;
    const camDist=Math.max(size.x,size.y,size.z,10)*1.8;
    camera.position.set(camDist,camDist,camDist);
    controls.target.set((bb.min.x+bb.max.x)/2,(bb.min.y+bb.max.y)/2,(bb.min.z+bb.max.z)/2);
    controls.update();
    previewStats.textContent=label+'\n\nDimensions (W × D × H):\n'+size.x.toFixed(1)+' × '+size.y.toFixed(1)+' × '+size.z.toFixed(1)+' mm\n\nVolume: '+(vol/1000).toFixed(2)+' cm³\nTriangles: '+polys.length+'\n\n'+(fits?'✓ Fits Adventurer 5M bed':'⚠ May exceed Adventurer 5M 220mm bed/height');
    resize();
  }catch(e){previewStats.textContent='Preview failed — '+e.message;}
};
resize();
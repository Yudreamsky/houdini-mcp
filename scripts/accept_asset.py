"""Reusable real GUI MCP acceptance for managed procedural recipes.

Requires an explicitly selected saved, clean GUI scene. Builds in a separate
scene/output directory, restores the source in finally, never overwrites output.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]
UPDATES={'pipe_support_sample':{'length':3.6,'diameter':.5},
         'pipe_elbow_sample':{'inlet_length':4.2,'outlet_length':3.6,'diameter':.5,'bend_radius':.9},
         'pipe_rack_sample':{'length':3.6,'diameter_1':.45,'diameter_2':.30,'spacing_12':.75,'spacing_23':.65,'rise_1':.06,'rise_2':0,'rise_3':.16}}
UPDATES['pipe_rack_reference']={'length':4.0,'support_pitch':1.2,'diameter_2':.30,'spacing_12':.60,'spacing_23':.58,'joint_offset_2':0}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ensure(condition,message):
    if not condition:raise RuntimeError(message)


async def run(args):
    output=Path(args.output).resolve();original=Path(args.expected_hip).resolve();hython=Path(args.hython).resolve()
    ensure(original.is_file(),'Expected source HIP must exist');ensure(hython.is_file(),'hython must exist')
    output.mkdir(parents=True,exist_ok=False)
    initial=json.loads(Path(args.parameters).read_text(encoding='utf-8')) if args.parameters else {}
    update=json.loads(Path(args.update).read_text(encoding='utf-8')) if args.update else UPDATES[args.recipe]
    ensure(isinstance(initial,dict) and isinstance(update,dict),'Parameter files must contain objects')
    source_hash=sha(original);instance_id='accept-'+uuid.uuid4().hex[:12]
    report=dict(recipe=args.recipe,instance_id=instance_id,output=str(output),checks=[],passed=False,
                source_hip=str(original),source_sha256=source_hash,visual_review='pending human/agent image review')
    def save(): (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    try:
        with (output/'mcp.stderr.log').open('w',encoding='utf-8') as log:
            async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'run_mcp.py')],env=os.environ.copy()),errlog=log) as streams:
                async with ClientSession(*streams) as c:
                    await c.initialize()
                    async def call(name,values=None,expect_error=False,label=None):
                        response=await c.call_tool(name,values or {})
                        ensure(bool(response.isError)==expect_error,f'{name}: unexpected error state: {response}' if response.isError else f'{name}: expected rejection')
                        data=[json.loads(v.text) for v in response.content if v.type=='text'] if not expect_error else [v.text for v in response.content if v.type=='text']
                        for i,item in enumerate(v for v in response.content if v.type=='image'):
                            raw=base64.b64decode(item.data);ensure(raw.startswith(b'\x89PNG\r\n\x1a\n'),'Expected PNG')
                            dest=output/((label or name)+'-'+str(i)+'.png');ensure(not dest.exists(),'Image output collision');dest.write_bytes(raw)
                            meta=data[i if name=='preview_asset_views' else 0]
                            if name=='preview_asset_views':ensure(sha(dest)==meta['sha256'],'Preview hash mismatch')
                            meta['native_image']=str(dest)
                        report['checks'].append(dict(tool=name,expected_error=expect_error,result=data));save()
                        return data[0] if len(data)==1 else data
                    async def code(source):return (await call('execute_code',{'code':source}))['result']
                    cap=await call('get_capabilities')
                    ensure(cap['ui_available'] and not cap['unsaved_changes'],'Use a clean saved GUI scene')
                    ensure(Path(cap['hip_path']).resolve()==original,'GUI scene differs from --expected-hip')
                    report['source_session']=cap
                    changed_scene=False
                    try:
                        changed_scene=True
                        await code('hou.hipFile.clear(suppress_save_prompt=True)\nresult=True')
                        catalog=await call('list_procedural_assets');ensure(any(v['id']==args.recipe and v['constraints'] for v in catalog['recipes']),'Missing recipe contract')
                        snapshot="result={'dirty':hou.hipFile.hasUnsavedChanges(),'nodes':[n.path() for n in hou.node('/').allSubChildren()],'libraries':sorted(hou.hda.loadedFiles())}"
                        before=await code(snapshot)
                        pre=await call('preflight_asset_instance',dict(instance_id=instance_id,recipe=args.recipe,parameters=initial))
                        ensure(pre['ready'] and pre['will_create'],'Initial preflight failed')
                        ensure(before==await code(snapshot),'Preflight changed scene/libraries')
                        first=await call('upsert_asset_instance',dict(instance_id=instance_id,recipe=args.recipe,parameters=initial));path=first['path']
                        ensure(first['created'] and first['check']['passed'],'Initial instance failed')
                        await call('save_scene',{'path':str(output/'checkpoint.hip')})
                        duplicate=await call('upsert_asset_instance',{'instance_id':instance_id})
                        ensure(duplicate['recipe']==args.recipe and not duplicate['changed'] and not duplicate['created'],'Inference/no-op failed')
                        ensure(not (await call('get_capabilities'))['unsaved_changes'],'No-op dirtied scene')
                        before=await code(snapshot)
                        bad_values={'diameter_1':.1,'wall_1':.03} if args.recipe in ('pipe_rack_sample','pipe_rack_reference') else {'diameter':.1,'wall':.03}
                        bad_code='wall_ratio_1' if args.recipe in ('pipe_rack_sample','pipe_rack_reference') else 'wall_ratio'
                        bad=await call('preflight_asset_instance',{'instance_id':instance_id,'parameters':bad_values})
                        ensure(not bad['ready'] and any(e['code']==bad_code for e in bad['errors']),'Missing structured constraint rejection')
                        other='pipe_elbow_sample' if args.recipe=='pipe_support_sample' else 'pipe_support_sample'
                        conflict=await call('preflight_asset_instance',{'instance_id':instance_id,'recipe':other})
                        ensure(not conflict['ready'],'Recipe mismatch accepted by preflight')
                        await call('upsert_asset_instance',{'instance_id':instance_id,'recipe':other},expect_error=True)
                        ensure(before==await code(snapshot),'Rejected requests changed scene')
                        pre=await call('preflight_asset_instance',{'instance_id':instance_id,'parameters':update})
                        ensure(pre['ready'] and pre['recipe']==args.recipe and pre['would_change'],'Update preflight failed or no change requested')
                        ensure(before==await code(snapshot),'Valid update preflight changed scene')
                        grown=await call('upsert_asset_instance',{'instance_id':instance_id,'parameters':update})
                        ensure(grown['check']['passed'] and grown['parameters']==pre['parameters'],'Write differs from preflight')
                        ensure(grown['check']['geometry_sha256']!=first['check']['geometry_sha256'],'Update did not change geometry')
                        await call('preview_asset_views',{'path':path,'views':['top','perspective']},label='updated')
                        final=await call('upsert_asset_instance',{'instance_id':instance_id,'parameters':first['parameters']})
                        ensure(final['check']['geometry_sha256']==first['check']['geometry_sha256'],'Reset geometry mismatch')
                        await call('preview_asset_views',{'path':path},label='default')
                        delivery=await code('from pathlib import Path\nimport shutil,hashlib\nn=hou.node('+repr(path)+')\nsrc=Path(n.type().definition().libraryFilePath())\ndst=Path('+repr(str(output))+')/src.name\nassert not dst.exists()\nshutil.copy2(src,dst)\nhou.hda.installFile(str(dst))\nfor d in hou.hda.definitionsInFile(str(dst)):d.setIsPreferred(True)\nassert Path(n.type().definition().libraryFilePath()).resolve()==dst.resolve()\nresult={"library":str(dst),"library_sha256":hashlib.sha256(dst.read_bytes()).hexdigest(),"type":n.type().name()}')
                        spec=dict(delivery,recipe=args.recipe,path=path,parameters=final['parameters'],geometry_sha256=final['check']['geometry_sha256'])
                        (output/'instance.json').write_text(json.dumps(spec,indent=2),encoding='utf-8')
                        saved=await call('save_scene',{'path':str(output/'sample.hip')});await call('open_scene',{'path':saved['path']})
                        reopened=await call('inspect_asset_instance',{'path':path})
                        ensure(reopened['passed'] and reopened['geometry_sha256']==spec['geometry_sha256'],'Saved geometry mismatch')
                        proc=await asyncio.to_thread(subprocess.run,[str(hython),str(ROOT/'scripts/verify_hda.py'),str(output/'instance.json'),str(output/'standalone.json')],capture_output=True,text=True,timeout=120,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                        (output/'standalone.log').write_text(proc.stdout+'\n'+proc.stderr,encoding='utf-8')
                        ensure(proc.returncode==0,'Standalone verification failed; see standalone.log')
                        report['standalone']=json.loads((output/'standalone.json').read_text())
                        if args.render:
                            setup=await code(render_setup(path))
                            hip=output/'render-demo.hip';await call('save_scene',{'path':str(hip)})
                            job=await call('render_frames',dict(hip_path=str(hip),asset_libraries=[spec['library']],asset_path=path,rop_path=setup['rop'],source_cop_node=setup['source'],composite_node=setup['composite'],start_frame=1,end_frame=1,width=960,height=540,renderer='mantra',quality='final',request_id=instance_id))
                            report['job_id']=job['job_id'];save();deadline=time.monotonic()+args.render_timeout
                            while True:
                                state=await call('get_render_status',{'job_id':job['job_id']})
                                if state['state']=='completed':break
                                ensure(state['state'] not in ('failed','interrupted','launch_unknown','cancelled'),'Render failed: '+state['state'])
                                if time.monotonic()>deadline:
                                    report['cancel_request']=await call('cancel_render',{'job_id':job['job_id']})
                                    raise TimeoutError('Render deadline; cancellation requested, not confirmed. Inspect recorded job before another run.')
                                await asyncio.sleep(1)
                            preview=await call('get_render_preview',{'job_id':job['job_id']},label='render')
                            report['render_warnings']=preview['visual_check']['warnings']
                        report['technical_checks_passed']=True
                    finally:
                        if changed_scene:
                            await call('open_scene',{'path':str(original),'discard_unsaved':True})
                            await code('hou.setFrame('+repr(cap['frame'])+')\nresult=True')
                            restored=await call('get_capabilities');report['restored_session']=restored
                            ensure(Path(restored['hip_path']).resolve()==original and not restored['unsaved_changes'],'Original session not restored cleanly')
                            ensure(sha(original)==source_hash,'Original HIP bytes changed')
                    report['passed']=True
    except BaseException as exc:
        report['error']=repr(exc);raise
    finally:
        report['source_unchanged']=sha(original)==source_hash;save()
        print(json.dumps({k:report.get(k) for k in ('passed','recipe','output','job_id','source_unchanged','error')},ensure_ascii=False))


def render_setup(path):
    return '''
asset=hou.node('''+repr(path)+''');obj=hou.node('/obj')
material=hou.node('/mat').createNode('principledshader::2.0','accept_material')
material.parmTuple('basecolor').set((1,1,1));material.parm('basecolor_usePointColor').set(1);material.parm('rough').set(.4)
asset.parent().parm('shop_materialpath').set(material.path())
bbox=asset.geometry().boundingBox();target=bbox.center();eye=target+hou.Vector3(5,5,7)
camera=obj.createNode('cam','accept_camera');camera.parm('projection').set(1)
camera.parm('orthowidth').set(max(bbox.sizevec().length()*1.3,2.0));camera.parmTuple('res').set((960,540))
z=(eye-target).normalized();x=hou.Vector3(0,1,0).cross(z).normalized();y=z.cross(x)
camera.setWorldTransform(hou.Matrix4((x[0],x[1],x[2],0,y[0],y[1],y[2],0,z[0],z[1],z[2],0,eye[0],eye[1],eye[2],1)))
for name,offset,power in [('key',(-2,4,4),35),('fill',(3,3,-2),22)]:
 light=obj.createNode('hlight::2.0',name);light.parmTuple('t').set(tuple(target+hou.Vector3(offset)));light.parm('light_intensity').set(power)
ambient=obj.createNode('ambient','ambient');ambient.parm('light_intensity').set(.15)
rop=hou.node('/out').createNode('ifd','accept_render');rop.parm('camera').set(camera.path())
comp=hou.node('/img').createNode('img','accept_preview');source=comp.createNode('file','source');source.parm('filename1').set('$HIP/placeholder.exr')
out=comp.createNode('null','OUT');out.setInput(0,source)
result={'rop':rop.path(),'source':source.path(),'composite':out.path()}
'''


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recipe',choices=list(UPDATES),required=True)
    parser.add_argument('--expected-hip',required=True,help='Current saved clean GUI file; restored after run')
    parser.add_argument('--output',required=True,help='New output directory; never overwritten')
    parser.add_argument('--hython',required=True,help='Matching Houdini hython executable for standalone HDA check')
    parser.add_argument('--parameters',help='Initial parameter overrides JSON file')
    parser.add_argument('--update',help='Update overrides JSON file; defaults to tested growth example')
    parser.add_argument('--render',action='store_true',help='Also create a generic Mantra setup and render one frame')
    parser.add_argument('--render-timeout',type=float,default=300)
    args=parser.parse_args()
    if args.render_timeout<=0:parser.error('render-timeout must be positive')
    asyncio.run(run(args))

if __name__=='__main__':main()

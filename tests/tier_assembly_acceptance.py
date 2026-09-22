"""Real SDK acceptance for a delivered snapshot HDA; run after native packaging."""
import asyncio,base64,hashlib,json,os,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evidence/upper-assembly-v01';ASSET=ROOT/'assets/upper-assembly-v01/candidate-02'

async def main():
 report={'mode':'external SDK stdio','checks':[]}
 with (OUT/'acceptance.log').open('w') as log:
  async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'run_mcp.py')],env=os.environ.copy()),errlog=log) as streams:
   async with ClientSession(*streams) as c:
    await c.initialize()
    report['tool_count']=len((await c.list_tools()).tools);assert report['tool_count']==22
    async def call(name,args=None,error=False):
     response=await c.call_tool(name,args or {});assert bool(response.isError)==error,response
     text=next(v.text for v in response.content if v.type=='text')
     value=text if error else json.loads(text)
     report['checks'].append(dict(tool=name,expected_error=error,result=value))
     return value,response
    original,_=await call('get_capabilities');assert not original['unsaved_changes']
    original_sha=hashlib.sha256(Path(original['hip_path']).read_bytes()).hexdigest()
    path='/obj/two_tier_assembly/asset'
    try:
     await call('open_scene',{'path':str(ASSET/'assembly.hip')})
     schema,_=await call('get_asset_schema',{'path':path});assert schema['assembly']['moving']==['upper_crossarm','rear_upper_crossarm','upper_duct_left','upper_duct_right']
     baseline,_=await call('inspect_asset_instance',{'path':path});assert baseline['passed'] and baseline['component_count']==218
     for height in (.45,.58,.80):
      value,_=await call('set_asset_parameters',{'path':path,'parameters':{'tier_y':height}})
      assert value['inspection']['passed'] and value['inspection']['fixed_components']==214
     for params in ({'tier_y':.44},{'tier_y':.81},{'tier_y':.55,'unknown':1}):
      await call('set_asset_parameters',{'path':path,'parameters':params},True)
     unchanged,_=await call('get_asset_schema',{'path':path});assert next(p for p in unchanged['parameters'] if p['name']=='tier_y')['value']==[.80]
     await call('set_asset_parameters',{'path':path,'parameters':{'tier_y':.58}})
     await call('save_scene',{'path':str(ASSET/'raised-580.hip')})
     await call('open_scene',{'path':str(ASSET/'raised-580.hip')})
     raised,_=await call('inspect_asset_instance',{'path':path});assert raised['passed'] and raised['tier_y']==.58
     await call('set_asset_parameters',{'path':path,'parameters':{'tier_y':.55}})
     reset,_=await call('inspect_asset_instance',{'path':path});assert reset==baseline
     # Existing name-filtered views now also work on the captured assembly.
     response=await c.call_tool('preview_asset_views',dict(path=path,views=['right','perspective'],width=960,height=720,
                    part_names=['upper_crossarm','rear_upper_crossarm','upper_duct_left','upper_duct_right','frame_redside','frame_blackside','rear_frame_redside','rear_frame_blackside']))
     assert not response.isError,response
     metadata=[json.loads(v.text) for v in response.content if v.type=='text']
     images=[v for v in response.content if v.type=='image'];assert len(images)==2
     for label,picture in zip(('upper-right','upper-perspective'),images):
      (ASSET/(label+'.png')).write_bytes(base64.b64decode(picture.data))
     report['views']=metadata
     report['passed']=True
    finally:
     await call('open_scene',{'path':original['hip_path'],'discard_unsaved':True})
     await call('execute_code',{'code':'hou.setFrame('+repr(original['frame'])+');result=True'})
     restored,_=await call('get_capabilities');assert not restored['unsaved_changes'] and restored['hip_path']==original['hip_path']
     assert hashlib.sha256(Path(original['hip_path']).read_bytes()).hexdigest()==original_sha
     report['restored_original']=True
     (OUT/'sdk-acceptance.json').write_text(json.dumps(report,indent=2))
 print(json.dumps({k:report[k] for k in ('passed','tool_count','restored_original')}),flush=True)
if __name__=='__main__':asyncio.run(main())

"""GUI SDK: exact-part focus, rejection and restoration using an existing saved sample."""
import argparse,asyncio,base64,hashlib,json,os,sys
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]


async def run(a):
    output=Path(a.output).resolve();output.mkdir(parents=True,exist_ok=False)
    original=Path(a.expected_hip).resolve();hip=Path(a.hip).resolve();spec=json.loads(Path(a.instance).read_text());report={'passed':False}
    source_hash=hashlib.sha256(original.read_bytes()).hexdigest()
    with (output/'mcp.log').open('w') as log:
        async with stdio_client(StdioServerParameters(command=sys.executable,args=[str(ROOT/'run_mcp.py')],env=os.environ.copy()),errlog=log) as streams:
            async with ClientSession(*streams) as c:
                await c.initialize()
                async def call(name,args=None,error=False,label=None):
                    r=await c.call_tool(name,args or {});assert bool(r.isError)==error,r
                    if error:return
                    values=[json.loads(v.text) for v in r.content if v.type=='text']
                    for i,v in enumerate(x for x in r.content if x.type=='image'):
                        raw=base64.b64decode(v.data);assert hashlib.sha256(raw).hexdigest()==values[i]['sha256']
                        (output/f'{label}-{i}.png').write_bytes(raw)
                    return values[0] if len(values)==1 else values
                async def code(s):return (await call('execute_code',{'code':s}))['result']
                cap=await call('get_capabilities');assert Path(cap['hip_path']).resolve()==original and not cap['unsaved_changes']
                await call('open_scene',{'path':str(hip)})
                try:
                    path=spec['path'];check=await call('inspect_asset_instance',{'path':path});assert check['passed']
                    snapshot="n=hou.node("+repr(path)+");result={'children':[x.path() for x in n.parent().children()],'display':n.parent().displayNode().path(),'render':n.parent().renderNode().path(),'selection':[x.path() for x in hou.selectedNodes()]}"
                    before=await code(snapshot)
                    names=[v['name'] for v in check['parts'] if v['name'].startswith('rack_pos_0_') and v['kind'] not in ('hanger','anchor','hanger_nut')]
                    views=await call('preview_asset_views',{'path':path,'views':['right','perspective'],'part_names':names},label='support')
                    for view in views[:-1]:
                        assert set(view['part_names'])==set(names)
                        assert view['bounds']['max'][0]-view['bounds']['min'][0]<.06
                    joint=[v['name'] for v in check['parts'] if v['name'].startswith('pipe2_') and v['kind']!='pipe']
                    joint_views=await call('preview_asset_views',{'path':path,'views':['perspective'],'part_names':joint},label='joint')
                    assert set(joint_views[0]['part_names'])==set(joint)
                    for filt in ({'part_names':['does_not_exist']},{'part_names':[]},{'part_names':[names[0]],'part_types':['pipe']}):
                        await call('preview_asset_views',dict(path=path,views=['front'],**filt),error=True)
                    after_state=await code(snapshot);report['before']=before;report['after']=after_state
                    assert before==after_state,(before,after_state)
                    after=await call('inspect_asset_instance',{'path':path});assert after['geometry_sha256']==check['geometry_sha256']
                    report.update(passed=True,support_views=views,joint_views=joint_views,invalid_filters_rejected=3,geometry_unchanged=True,display_selection_children_restored=True)
                finally:
                    await call('open_scene',{'path':str(original),'discard_unsaved':True})
                    await code('hou.setFrame('+repr(cap['frame'])+');result=True')
                    restored=await call('get_capabilities');assert not restored['unsaved_changes'] and Path(restored['hip_path']).resolve()==original
                    assert hashlib.sha256(original.read_bytes()).hexdigest()==source_hash
                    report['restored_session']=restored
                    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'passed':report['passed'],'output':str(output)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('hip','instance','expected-hip','output'):parser.add_argument('--'+key,required=True)
    asyncio.run(run(parser.parse_args()))

"""Fresh hython: verify_hda.py INSTANCE_JSON REPORT_JSON. No repo imports."""
import hashlib
import json
import sys
from pathlib import Path
import hou


def main():
    spec=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    output=Path(sys.argv[2]).resolve()
    if output.exists():raise FileExistsError('Verification report already exists')
    if hou.isUIAvailable() or hou.node('/obj').children():raise RuntimeError('Use fresh empty headless hython')
    repo_src=(Path(__file__).resolve().parents[1]/'src').resolve()
    if any(Path(p).resolve()==repo_src for p in sys.path if p):raise RuntimeError('Repository src must not be on sys.path')
    library=Path(spec['library']).resolve()
    if hashlib.sha256(library.read_bytes()).hexdigest()!=spec['library_sha256']:raise ValueError('HDA file changed')
    hou.hda.installFile(str(library))
    obj=hou.node('/obj').createNode('geo',run_init_scripts=False);node=obj.createNode(spec['type'])
    for name,value in spec['parameters'].items():node.parm(name).set(value)
    geo=node.geometry()
    if node.errors():raise RuntimeError(str(node.errors()))
    digest=hashlib.sha256()
    for p in geo.prims():digest.update(json.dumps([p.attribValue('name'),[v.point().number() for v in p.vertices()]]).encode())
    for p in geo.points():digest.update(json.dumps(tuple(p.position())).encode())
    if digest.hexdigest()!=spec['geometry_sha256']:raise ValueError('Standalone geometry mismatch')
    result=dict(passed=True,houdini=hou.applicationVersionString(),points=len(geo.points()),primitives=len(geo.prims()),
                geometry_sha256=digest.hexdigest(),repository_src_on_path=False,library=str(library))
    output.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))

if __name__=='__main__':main()

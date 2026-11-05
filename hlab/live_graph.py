"""Atomic live OP edits. One private undo object per successful batch, none on failure."""
import hashlib
import json
import math
import os
import re
import tempfile
import time
import uuid
from pathlib import Path

import hou

from .storage import home

SESSION = uuid.uuid4().hex
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
ROOTS = {"obj", "mat", "stage", "out", "ch", "img", "tasks", "shop"}
HSCRIPT_EXEC = re.compile(r"\b(?:python(?:expr[fs]?)?|system(?:ES|RAW)?|execute[be]?|run[be]?|evals?|unix)\s*\(", re.I)
SCRIPT_LABEL = re.compile(r"\b(?:script|callback|python|hscript|command|executable|program)\b", re.I)
BACKTICK = re.compile(r"(?<!\\)(?:\\\\)*`")


def checked_path(path):
    if not isinstance(path, str):
        raise ValueError("Expected an absolute node path")
    pieces = path.split("/")
    if len(pieces) < 3 or pieces[0] or pieces[1] not in ROOTS or any(p in (".", "..", "") for p in pieces[2:]):
        raise ValueError(f"Choose a child OP in an editable context: {path}")
    return path


def node(path):
    result = hou.node(checked_path(path))
    if not isinstance(result, hou.OpNode):
        raise ValueError(f"Missing OP: {path}")
    return result


def parent_name(path):
    parent, _, name = checked_path(path).rpartition("/")
    network = hou.node(parent)
    if not network or not network.isNetwork() or not NAME.fullmatch(name):
        raise ValueError(f"Invalid parent or node name: {path}")
    return network, name


def exception_gate(path, value):
    if os.environ.get("HOUDINI_RESEARCH_ALLOW_CODE") != "1":
        raise ValueError(f"Code-capable write disabled at {path}; opt in on the Houdini host with HOUDINI_RESEARCH_ALLOW_CODE=1")
    event = dict(time=time.time(), path=path, sha256=hashlib.sha256(str(value).encode()).hexdigest())
    target = home() / "audit" / "graph-code.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf8") as file:
        file.write(json.dumps(event) + "\n")


def code_type(nt):
    name = nt.name().lower().split("::")
    return any(re.search(r"(?:python|shell|command|hscript|scriptserver|hdaevent|^unix$)", part) for part in name)


def built_in(nt):
    """Houdini's own type: no asset definition, or one from a library under $HFS."""
    definition = nt.definition()
    return definition is None or Path(definition.libraryFilePath()).resolve().is_relative_to(
        Path(hou.expandString("$HFS")).resolve())


def check_type(nt, path, template):
    if template:
        if template != "fireworks.trails" or nt.nameWithCategory() != "Sop/python":
            raise ValueError("The bundled fireworks.trails template requires Sop/python")
        return
    if code_type(nt) or not built_in(nt):
        exception_gate(path, nt.nameWithCategory())


def check_value(p, op):
    value = op["value"]
    if type(value) not in (int, float, bool, str) or (isinstance(value, float) and not math.isfinite(value)):
        raise ValueError(f"Expected a finite scalar or string at {p.path()}")
    p.node().updateParmStates()
    if p.isLocked() or p.isDisabled():
        raise ValueError(f"Locked or disabled: {p.path()}")
    if (p.keyframes() or p.getReferencedParm() != p) and not op.get("replace_expression"):
        raise ValueError(f"Animated or linked: {p.path()}; specify replace_expression to replace it")
    pt = p.parmTemplate()
    if pt.type() not in (hou.parmTemplateType.Float, hou.parmTemplateType.Int, hou.parmTemplateType.String, hou.parmTemplateType.Toggle, hou.parmTemplateType.Menu):
        raise ValueError(f"Unsupported parameter type at {p.path()}")
    lang = op.get("expression")
    if lang and (lang not in ("hscript", "python") or not isinstance(value, str)):
        raise ValueError("Provide an expression string and a supported language")
    if "expect" in op and op["expect"] is not None and p.eval() != op["expect"]:
        raise ValueError(f"Expectation failed at {p.path()}: current value {p.eval()!r}")
    tags = pt.tags()
    name = p.name().lower()
    is_vex = (p.node().type().name().split("::")[0].endswith("wrangle") and name == "snippet") or tags.get("editorlang","").lower()=="vex"
    scripted = bool(pt.scriptCallback()) or (not is_vex and (
        tags.get("editorlang","").lower() in {"python","hscript","script"} or
        (isinstance(value,str) and (code_type(p.node().type()) or
         SCRIPT_LABEL.search(pt.label()) or name in {"cmd","postwrite","soho_program"} or
         any(s in name for s in ("callback","python","command","preframe","postframe","prerender","postrender","preflight","postflight","pipecmd"))
         or ("script" in name and "descript" not in name)))))
    # Plain strings and VEX can mention run() as text. Houdini evaluates HScript in
    # expressions and backtick-interpolated sections, including those inside VEX.
    embedded = BACKTICK.split(value)[1::2] if isinstance(value, str) and "`" in value else ()
    if lang == "python" or scripted or any(HSCRIPT_EXEC.search(expr) for expr in (
            [value] if lang == "hscript" else embedded)):
        exception_gate(p.path(), value)


def get_literal(p):
    return p.unexpandedString() if isinstance(p.parmTemplate(), hou.StringParmTemplate) and not p.keyframes() else p.eval()


def brief(p):
    """A set step's value. Text over 200 characters returns a preview, length and sha256 of the stored
    text, which a plain set leaves equal to the text sent; evaluation would expand $HIP in VEX strings."""
    value = p.eval()
    if not isinstance(value, str) or len(value) <= 200:
        return value
    text = get_literal(p)
    return {"preview": text[:120], "length": len(text), "sha256": hashlib.sha256(text.encode()).hexdigest()}


def flags_of(network):
    return [(n.name(), n.isDisplayFlagSet() if hasattr(n,"isDisplayFlagSet") else None,
             n.isRenderFlagSet() if hasattr(n,"isRenderFlagSet") else None) for n in network.children()]


def restore_flags(network_path, before):
    parent = hou.node(network_path)
    if parent is None:
        return
    for desired in (False, True):
        for name, display, render in before:
            n = parent.node(name)
            if n is not None:
                if display is desired and n.isDisplayFlagSet() != desired:
                    n.setDisplayFlag(desired)
                if render is desired and n.isRenderFlagSet() != desired:
                    n.setRenderFlag(desired)


def input_wires(n):
    return sorted((c.inputIndex(), c.inputItem().path(), c.inputItemOutputIndex()) for c in n.inputConnections())


def restore_inputs(path, before):
    n = node(path)
    # Multi-input operators compact their connectors on disconnect. Restore shifted
    # siblings as well as the removed wire, retaining any unrelated dots/indirect inputs.
    current = set(input_wires(n))
    for i, src, out in before:
        if (i, src, out) not in current:
            item = hou.item(src)
            if item is None:
                raise RuntimeError(f"Cannot restore missing connection source: {src}")
            n.setInput(i, item, out)
    keep = {i for i, _, _ in before}
    for i, _, _ in reversed(input_wires(n)):
        if i not in keep:
            n.setInput(i, None)


class Batch:
    def __init__(self):
        self.steps = []
        self.files = None

    def backup(self, item):
        if self.files is None:
            self.files = tempfile.TemporaryDirectory(prefix="houdini-graph-undo-")
        path = Path(self.files.name) / (uuid.uuid4().hex + ".cpio")
        item.parent().saveItemsToFile([item], str(path))
        return path

    def do(self, forward, inverse):
        try:
            forward()
        except Exception:
            # Set may have removed keyframes; create/flags may have partially succeeded.
            inverse()
            raise
        self.steps.append((forward, inverse))

    def undo(self):
        with hou.undos.disabler():
            failures = []
            for _, inverse in reversed(self.steps):
                try:
                    inverse()
                except Exception as exc:
                    failures.append(str(exc))
            if failures:
                raise RuntimeError("Rollback incomplete: " + "; ".join(failures))

    def redo(self):
        with hou.undos.disabler():
            for forward, _ in self.steps:
                forward()


def create(batch, op, label):
    path = op["path"]
    parent, name = parent_name(path)
    nt = hou.nodeType(parent.childTypeCategory(), op["type"])
    if not nt or hou.node(path):
        raise ValueError(f"Unknown exact node type or occupied path: {op['type']} / {path}")
    template = op.get("template")
    check_type(nt, path, template)
    pp = parent.path()
    flags = flags_of(parent)
    # Houdini's own creation scripts add parameters such as a camera's resx and focal or a geo
    # object's vm_ render properties. Other assets' scripts stay off.
    init = built_in(nt)
    def forward():
        n = hou.node(pp).createNode(nt.name(), name, run_init_scripts=init, exact_type_name=True)
        if template:
            from .scene import configure_trails
            configure_trails(n)
        n.setColor(hou.Color((.22,.55,.57)))
        n.setUserData("created_by","mcp")
        n.setUserData("mcp_session",SESSION)
        n.setUserData("mcp_label",label)
        n.moveToGoodPosition(move_inputs=False, move_outputs=False, move_unconnected=False)
    def inverse():
        n = hou.node(path)
        if n: n.destroy()
        restore_flags(pp,flags)
    batch.do(forward,inverse)
    return path


def edit_one(batch, op, label, allow_delete):
    path = checked_path(op["path"])
    if op["op"] == "create":
        return create(batch,op,label)
    n = node(path)
    parent = n.parent()
    if not parent.isEditable():
        raise ValueError(f"Locked network: {parent.path()}")
    typ = op["op"]
    if typ == "set":
        p = n.parm(op["parm"])
        if not p or p.node() != n: raise ValueError(f"No local parameter {op['parm']} on {path}")
        check_value(p,op)
        keys = p.keyframes()
        prior = None if keys else get_literal(p)
        extrapolation = [p.keyframeExtrapolation(end) for end in (False, True)] if keys else []
        parm_name = p.name()
        def write(value, expr=None, saved=()):
            p = node(path).parm(parm_name)
            if p.keyframes():p.deleteAllKeyframes()
            if saved:
                p.setKeyframes(saved)
                for end, mode in zip((False, True), extrapolation):
                    p.setKeyframeExtrapolation(end, mode)
            elif expr:p.setExpression(value, hou.exprLanguage.Python if expr=="python" else hou.exprLanguage.Hscript)
            else:p.set(value,follow_parm_reference=False)
        batch.do(lambda:write(op["value"],op.get("expression")),lambda:write(prior,saved=keys))
    elif typ == "connect":
        i, o = op.get("input",0), op.get("output",0)
        source = op["source"]
        if not 0 <= i < n.type().maxNumInputs() or o < 0:
            raise ValueError("Input or output connector index out of bounds")
        if source:
            start = node(source)
            if o >= len(start.outputConnectors()):raise ValueError("Output connector index out of bounds")
            if start.parent()!=parent or start==n or n in start.inputAncestors(): raise ValueError("Cycle or differing network")
        old = next((c for c in n.inputConnections() if c.inputIndex()==i),None)
        if old and old.inputItem()!=old.inputNode():
            raise ValueError("Reconnect the existing indirect network item explicitly before editing this input")
        before = input_wires(n)
        def connect(src, out):
            node(path).setInput(i,node(src) if src else None,out)
        batch.do(lambda:connect(source,o),lambda:restore_inputs(path,before))
    elif typ == "flags":
        pp = parent.path()
        before = flags_of(parent)
        edits = [(flag,op[flag]) for flag in ("display","render") if op.get(flag) is not None]
        if not edits: raise ValueError("Specify display or render")
        for flag, value in edits:
            if type(value) is not bool or not hasattr(n,"set"+flag.title()+"Flag"):
                raise ValueError(f"Unavailable or invalid {flag} flag on {path}")
        def set_flags():
            for flag, value in edits:
                getattr(node(path),"set"+flag.title()+"Flag")(value)
        batch.do(set_flags,lambda:restore_flags(pp,before))
    elif typ == "rename":
        new_name = op["name"]; old_name=n.name()
        if not NAME.fullmatch(new_name) or parent.node(new_name):raise ValueError(f"Invalid or occupied name: {new_name}")
        new_path=parent.path()+"/"+new_name
        batch.do(lambda:node(path).setName(new_name),lambda:hou.node(new_path) and node(new_path).setName(old_name))
        return new_path
    elif typ == "delete":
        if path not in allow_delete and n.userData("mcp_session")!=SESSION:
            raise ValueError(f"List {path} in allow_delete to remove an existing node")
        if not n.isEditableInsideLockedHDA():raise ValueError(f"Locked asset: {path}")
        pp=parent.path();before=flags_of(parent)
        box = n.parentNetworkBox()
        box_name = box.name() if box else None
        if any(c.inputItem()!=c.inputNode() for c in n.inputConnections()):
            raise ValueError("Delete involving network dots or indirect wiring is not supported")
        wires = {path:input_wires(n)}
        for c in n.outputConnections():
            if c.outputItem()!=c.outputNode():
                raise ValueError("Delete involving network dots or indirect wiring is not supported")
            dst = c.outputNode()
            if dst.path() not in wires:
                wires[dst.path()] = input_wires(dst)
        backup=batch.backup(n)
        def restore():
            if not hou.node(path):
                hou.node(pp).loadItemsFromFile(str(backup))
                if box_name:
                    hou.node(pp).findNetworkBox(box_name).addItem(node(path))
                for dst, before_inputs in wires.items():
                    restore_inputs(dst, before_inputs)
                restore_flags(pp,before)
        batch.do(lambda:node(path).destroy(),restore)
    else: raise ValueError(f"Unknown graph operation: {typ}")
    return path


def edit(ops, label="graph_edit", allow_delete=(), require_clean=True):
    if not 1<=len(ops)<=128 or not label.strip() or len(label)>100:
        raise ValueError("Supply 1–128 operations and a short label")
    batch=Batch()
    results=[]
    step=0
    try:
        with hou.undos.disabler():
            for step,op in enumerate(ops,1):
                path=edit_one(batch,op,label,set(allow_delete))
                n=hou.node(path)
                result=dict(step=step,op=op["op"],path=path)
                if op["op"]=="create":result["init_scripts"]=built_in(n.type())
                if op["op"]=="set":result["value"]=brief(n.parm(op["parm"]))
                if op["op"]=="flags":
                    result["display"]=n.isDisplayFlagSet() if hasattr(n,"isDisplayFlagSet") else None
                    result["render"]=n.isRenderFlagSet() if hasattr(n,"isRenderFlagSet") else None
                if op["op"]=="connect":result["inputs"]=[p.path() if p else None for p in n.inputs()]
                results.append(result)
            reports={}
            for row in results:
                n=hou.node(row["path"])
                if n is None:continue
                if n.path() not in reports:
                    if isinstance(n, hou.SopNode):n.geometry()
                    reports[n.path()]={"type":n.type().nameWithCategory(),"errors":list(n.errors()),"warnings":list(n.warnings())}
                row.update(reports[n.path()])
                if require_clean and row["errors"]:
                    step=row["step"];raise ValueError("; ".join(row["errors"]))
    except Exception as exc:
        batch.undo()
        raise ValueError(f"Step {step} rolled back: {exc}") from exc
    with hou.undos.group("MCP: "+label):
        hou.undos.add(batch,"MCP: "+label)
    return {"steps":results, "label":"MCP: "+label}

"""Portable render option and evidence helpers (no Houdini import)."""
import re
import json


def options(renderer='mantra', quality='preview'):
    if renderer not in ('mantra', 'karma_xpu'):
        raise ValueError('renderer must be mantra or karma_xpu')
    if quality not in ('preview', 'final'):
        raise ValueError('quality must be preview or final')
    return {'renderer': renderer, 'quality': quality,
            'pixel_samples': (16 if quality == 'preview' else 64) if renderer == 'karma_xpu' else (4 if quality == 'preview' else 16)}


def device_evidence(log, frame):
    """Only attribute device contribution from this frame's completed log block."""
    blocks = list(re.finditer(r'>>> Render[^\n]*frame:\s*(-?\d+)', log))
    selected = ''
    for index, match in enumerate(blocks):
        if int(match.group(1)) == frame:
            selected = log[match.end():blocks[index + 1].start() if index + 1 < len(blocks) else len(log)]
    devices = []
    for block in re.split(r'\nDevice \d+\s*\n', selected)[1:]:
        kind = re.search(r'^Type\s*:\s*(.+)$', block, re.M)
        name = re.search(r'^Name\s*:\s*(.+)$', block, re.M)
        contribution = re.search(r'^Contrib\s*:\s*([\d.]+)%', block, re.M)
        if kind and name and contribution:
            devices.append(dict(type=kind.group(1).strip(), name=name.group(1).strip(), contribution_percent=float(contribution.group(1))))
    return {'verified': any(d['type'].lower() == 'optix' and d['contribution_percent'] > 0 for d in devices),
            'devices': devices, 'source': 'husk completed-frame render statistics', 'frame': frame}


def cancellation_receipt(folder, pending):
    """Prove a known pre-frame cancellation, without masking a failed current frame."""
    stopped = folder / 'renderer-stop.json'
    if not stopped.exists() or not (folder / 'cancel.json').exists():
        return None
    stop = json.loads(stopped.read_text())
    if (stop.get('reason') != 'cancel_requested' or stop.get('frame') not in pending
            or (folder / f"start_{stop['frame']:04}.json").exists()
            or not all((folder / p.name.replace('start_', 'ready_')).exists() for p in folder.glob('start_*.json'))):
        return None
    return stop

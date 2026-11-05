"""Finite tiled WFC. Rows run bottom to top; sockets match exact opposite-edge labels."""
import math
import random
from collections import deque


class Contradiction(ValueError):
    pass


def constrain_passages(state, links, open_tiles, loop_free):
    """Keep possible passages connected; force bridges and optionally forbid cycles."""
    n = len(state)
    parent = list(range(n))
    def root(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    graph = [[] for _ in state]
    optional = []
    for i, j, side, opposite in links:
        if state[i].isdisjoint(open_tiles[side]):
            continue
        graph[i].append(j)
        graph[j].append(i)
        if state[i] <= open_tiles[side]:
            if loop_free:
                a, b = root(i), root(j)
                if a == b:
                    raise Contradiction("Forced passages form a cycle")
                parent[a] = b
        else:
            optional.append((i,j,side,opposite))

    order = [-1]*n
    low = [0]*n
    bridges = set()
    visited = 0
    def visit(u, previous):
        nonlocal visited
        order[u] = low[u] = visited
        visited += 1
        for v in graph[u]:
            if v == previous:
                continue
            if order[v] >= 0:
                low[u] = min(low[u], order[v])
                continue
            visit(v, u)
            low[u] = min(low[u], low[v])
            if low[v] > order[u]:
                bridges.add((min(u,v), max(u,v)))
    visit(0,-1)
    if visited != n:
        raise Contradiction(f"Possible passages disconnected: {visited}/{n} cells reachable")
    changed = set()
    for i, j, side, opposite in optional:
        required = (i,j) in bridges
        if not required and not (loop_free and root(i) == root(j)):
            continue
        for pos, direction in ((i,side),(j,opposite)):
            before = len(state[pos])
            if required:
                state[pos].intersection_update(open_tiles[direction])
            else:
                state[pos].difference_update(open_tiles[direction])
            if len(state[pos]) != before:
                changed.add(pos)
    return sorted(changed)


def solve(columns, rows, tiles, seed, cells=(), edges=None, connected_socket=None, loop_free=False):
    if not 1 <= columns * rows <= 256 or min(columns, rows) < 1:
        raise ValueError("Use 1 to 256 cells")
    by_name = {tile["name"]: tile for tile in tiles}
    if not tiles or len(tiles) != len(by_name) or len(tiles) > 64:
        raise ValueError("Use 1 to 64 uniquely named tiles")
    names = tuple(by_name)
    weights = [by_name[n]["weight"] for n in names]
    if any(not math.isfinite(w) or w <= 0 for w in weights):
        raise ValueError("Tile weights must be positive and finite")
    directions = [("west","east",-1,0), ("east","west",1,0), ("south","north",0,-1), ("north","south",0,1)]
    if loop_free and connected_socket is None:
        raise ValueError("loop_free requires a connected_socket")
    adjacent = [[{j for j, b in enumerate(tiles) if a[side] == b[opposite]} for a in tiles]
                for side, opposite, _, _ in directions]
    domains = [set(range(len(tiles))) for _ in range(columns * rows)]
    neighbours = [[] for _ in domains]
    for i, domain in enumerate(domains):
        x, y = i % columns, i // columns
        for k, (side, _, dx, dy) in enumerate(directions):
            nx, ny = x+dx, y+dy
            if 0 <= nx < columns and 0 <= ny < rows:
                neighbours[i].append((k, ny*columns+nx))
            elif edges and edges.get(side) is not None:
                domain.intersection_update(j for j,t in enumerate(tiles) if t[side] == edges[side])
    for pin in cells:
        x, y, allowed = pin["x"], pin["y"], pin["allow"]
        if not (0 <= x < columns and 0 <= y < rows) or not allowed or any(n not in by_name for n in allowed):
            raise ValueError(f"Invalid cell constraint at ({x}, {y})")
        domains[y*columns+x].intersection_update(names.index(n) for n in allowed)

    rng = random.Random(seed)
    stats = dict(decisions=0, propagated_removals=0, backtracks=0)
    if connected_socket is not None:
        open_tiles = [{j for j,t in enumerate(tiles) if t[side] == connected_socket} for side,_,_,_ in directions]
        links = [(i,j,k,k^1) for i, adjacent_cells in enumerate(neighbours) for k,j in adjacent_cells if i<j]

    def conflict(i):
        return Contradiction(f"No compatible assignment at cell ({i % columns}, {i // columns})")

    def propagate_local(state, pending):
        queue = deque(pending)
        while queue:
            i = queue.popleft()
            if not state[i]:
                raise conflict(i)
            for k, n in neighbours[i]:
                possible = set().union(*(adjacent[k][j] for j in state[i]))
                lost = state[n] - possible
                if lost:
                    stats["propagated_removals"] += len(lost)
                    state[n] -= lost
                    if not state[n]:
                        raise conflict(n)
                    queue.append(n)

    def propagate(state, pending):
        propagate_local(state, pending)
        if connected_socket is not None:
            while True:
                changed = constrain_passages(state, links, open_tiles, loop_free)
                if not changed:
                    break
                propagate_local(state, changed)

    def entropy(domain):
        ws = [weights[j] for j in sorted(domain)]
        total = sum(ws)
        return math.log(total) - sum(v*math.log(v) for v in ws)/total

    def collapse(state):
        undecided = [i for i,d in enumerate(state) if len(d)>1]
        if not undecided:
            return state
        i = min(undecided, key=lambda k: (entropy(state[k]), rng.random()))
        options = sorted(state[i])
        last = None
        while options:
            if stats["decisions"] >= 10000:
                raise RuntimeError("Search budget exceeded (10000 decisions)")
            j = rng.choices(options, weights=[weights[k] for k in options], k=1)[0]
            options.remove(j)
            stats["decisions"] += 1
            trial = [d.copy() for d in state]
            trial[i] = {j}
            try:
                propagate(trial, [i])
                return collapse(trial)
            except Contradiction as exc:
                last = exc
                stats["backtracks"] += 1
        raise last

    propagate(domains, range(len(domains)))
    solved = [names[next(iter(d))] for d in collapse(domains)]
    return {"seed": seed, "layout": [solved[i:i+columns] for i in range(0,len(solved),columns)], "stats": stats}

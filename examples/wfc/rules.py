"""Small, ordered socket grammars used by the public WFC examples and regression tests."""

from collections import deque

STEPS = (("W", "west", -1, 0), ("E", "east", 1, 0),
         ("S", "south", 0, -1), ("N", "north", 0, 1))
OPPOSITE = dict(W="E", E="W", S="N", N="S")
COLS, ROWS = 13, 11
ENTRANCE, EXIT = (0, 1), (12, 9)


def maze_request(seed=4):
    """143 connected cells, no loops, exactly two exterior gates."""
    tiles = []
    for mask in range(1, 16):
        label = "".join(s for i, (s, _, _, _) in enumerate(STEPS) if mask & (1 << i))
        weight = {1: .55, 2: 2.8, 3: .76, 4: .16}[len(label)]
        if label in ("WE", "SN"):
            weight = 1.7
        tiles.append(dict(name=label, weight=weight,
                          **{side: "way" if s in label else "wall" for s, side, _, _ in STEPS}))
    cells = []
    for y in range(ROWS):
        for x in range(COLS):
            required = {}
            for s, _, dx, dy in STEPS:
                if not (0 <= x + dx < COLS and 0 <= y + dy < ROWS):
                    required[s] = ((x, y) == ENTRANCE and s == "W") or ((x, y) == EXIT and s == "E")
            if (x, y) in (ENTRANCE, EXIT):
                required.update(W=True, E=True, N=False, S=False)
            if required:
                cells.append(dict(x=x, y=y, allow=[t["name"] for t in tiles
                             if all((s in t["name"]) == opened for s, opened in required.items())]))
    return dict(columns=COLS, rows=ROWS, tiles=tiles, cells=cells, seed=seed,
                connected_socket="way", loop_free=True)


def maze_metrics(layout):
    """Check actual connections and gates independently of the solver; trace the exit route."""
    if len(layout) != ROWS or any(len(row) != COLS for row in layout):
        raise ValueError("Expected a 13 by 11 maze")
    neighbours = {(x, y): [] for y in range(ROWS) for x in range(COLS)}
    gates = []
    for (x, y), adjacent in neighbours.items():
        for s, _, dx, dy in STEPS:
            if s not in layout[y][x]:
                continue
            other = x + dx, y + dy
            if other in neighbours:
                if OPPOSITE[s] not in layout[other[1]][other[0]]:
                    raise ValueError(f"Mismatched passage at {(x, y, s)}")
                adjacent.append(other)
            else:
                gates.append(((x, y), s))
    if set(gates) != {(ENTRANCE, "W"), (EXIT, "E")}:
        raise ValueError("Expected only the west entrance and east exit")
    parents = {ENTRANCE: None}
    pending = deque([ENTRANCE])
    while pending:
        current = pending.popleft()
        for neighbour in neighbours[current]:
            if neighbour not in parents:
                parents[neighbour] = current
                pending.append(neighbour)
    route = []
    if EXIT in parents:
        current = EXIT
        while current is not None:
            route.append(list(current))
            current = parents[current]
        route.reverse()
    return dict(reachable=len(parents), interior_edges=sum(map(len, neighbours.values())) // 2,
                gates=len(gates), route=route, steps=max(0, len(route) - 1))


def facade_request(seed=3, lock_from=None, lock_columns=6):
    """12 bays by two bands, with paired louvers, a door/hood and vertical risers."""
    def tile(name, weight=1., west="j", east="j", south="face", north="face"):
        return dict(name=name, weight=weight, west=west, east=east, south=south, north=north)

    tiles = [tile("END_L", west="extL", south="cap", north="cap"),
             tile("END_R", east="extR", south="cap", north="cap"),
             tile("SOLID", 2.5), tile("FINS", 1.8),
             tile("PAIR_L", 1.2, east="span"), tile("PAIR_R", 1.2, west="span"),
             tile("DOOR", north="head"), tile("HOOD", south="head"),
             tile("BASE", .75, north="shaft"), tile("RISER", .75, south="shaft")]
    cells = []
    for y in range(2):
        for x in range(12):
            choices = ["SOLID", "FINS", "PAIR_L", "PAIR_R"] + (["BASE"] if y == 0 else ["RISER", "HOOD"])
            if x in (0, 11):
                choices = ["END_L" if x == 0 else "END_R"]
            elif (x, y) == (2, 0):
                choices = ["DOOR"]
            cells.append(dict(x=x, y=y, allow=choices))
    if lock_from is not None:
        if len(lock_from) != 2 or any(len(row) != 12 for row in lock_from) or not 0 <= lock_columns <= 12:
            raise ValueError("Lock source must be a 12 by 2 facade; lock_columns must be 0 to 12")
        cells.extend(dict(x=x, y=y, allow=[row[x]]) for y, row in enumerate(lock_from)
                     for x in range(lock_columns))
    return dict(columns=12, rows=2, tiles=tiles, cells=cells, seed=seed)

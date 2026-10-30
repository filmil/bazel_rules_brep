from build123d import Align, Box, Cylinder, Pos

HOLES = [(-20, -10), (20, -10), (-20, 10), (20, 10)]


def build(params):
    # A tray 60 x 40 inside, 2 mm walls and floor (floor top at z = 0), and a
    # 5 mm boss under each mounting hole, its top at 4. params: pins puts a
    # 3 mm pin on each boss instead of a 2.5 mm hole, up through the board;
    # floor leaves the walls out.
    a = (Align.CENTER, Align.CENTER, Align.MIN)
    if params.get("floor"):
        tray = Pos(0, 0, -2) * Box(64, 44, 2, align=a)
    else:
        tray = Pos(0, 0, -2) * Box(64, 44, 12, align=a) - Pos(0, 0, 0) * Box(60, 40, 12, align=a)
    for x, y in HOLES:
        tray += Pos(x, y, 0) * Cylinder(2.5, 4, align=a)
        if params.get("pins"):
            tray += Pos(x, y, 4) * Cylinder(1.5, 3, align=a)
        else:
            tray -= Pos(x, y, 0) * Cylinder(1.25, 4, align=a)
    return tray

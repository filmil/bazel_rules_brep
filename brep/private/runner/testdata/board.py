from build123d import Axis, Box, Compound, Cylinder, Pos, fillet

HOLES = [(-20, -10), (20, -10), (-20, 10), (20, 10)]


def build(params):
    # A 50 x 30 x 1.6 mm board, bottom at z = 0, rounded corners, four
    # 3.2 mm mounting holes. params: shift moves the first hole along X;
    # notch cuts a half-round notch, 2 mm in radius, into the long edge;
    # parts puts two parts on top, a tall can and a box.
    shift = float(params.get("shift", 0))
    board = Pos(0, 0, 0.8) * Box(50, 30, 1.6)
    board = fillet(board.edges().filter_by(Axis.Z), 2)
    for i, (x, y) in enumerate(HOLES):
        board -= Pos(x + (shift if i == 0 else 0), y, 0.8) * Cylinder(1.6, 4)
    if params.get("notch"):
        board -= Pos(0, 15, 0.8) * Cylinder(2, 4)
    if params.get("parts"):
        board = Compound([board, Pos(0, 0, 6.6) * Cylinder(3, 10), Pos(10, 0, 2.6) * Box(6, 4, 2)])
    return board

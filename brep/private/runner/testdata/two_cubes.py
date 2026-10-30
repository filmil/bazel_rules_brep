from build123d import Box, Pos


def build(params):
    # Two 1 mm cubes, 3 mm apart: one part, two solids.
    return Pos(0, 0, 0) * Box(1, 1, 1) + Pos(3, 0, 0) * Box(1, 1, 1)

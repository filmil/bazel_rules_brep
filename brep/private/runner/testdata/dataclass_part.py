from dataclasses import dataclass

from build123d import Box


@dataclass
class Size:
    x: float
    y: float
    z: float


def build(params):
    s = Size(1, 1, 1)
    return Box(s.x, s.y, s.z)

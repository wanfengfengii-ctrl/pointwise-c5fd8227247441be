from dataclasses import dataclass
from fractions import Fraction


Point = tuple[Fraction, Fraction]
Polygon = tuple[Point, ...]
Triangle = tuple[Point, Point, Point]


@dataclass(frozen=True)
class AffineForm:
    u: Fraction
    v: Fraction
    constant: Fraction

    def evaluate(self, point: Point) -> Fraction:
        x, y = point
        return self.u * x + self.v * y + self.constant

    def at_least(self, bound: Fraction) -> 'AffineForm':
        return AffineForm(self.u, self.v, self.constant - bound)

    def at_most(self, bound: Fraction) -> 'AffineForm':
        return AffineForm(-self.u, -self.v, bound - self.constant)


def polygon_area(polygon: Polygon) -> Fraction:
    if len(polygon) < 3:
        return Fraction(0)
    following = polygon[1:] + polygon[:1]
    twice_area = sum((x * t - y * s for (x, y), (s, t) in zip(polygon, following)), Fraction(0))
    return abs(twice_area) / 2


def clip_polygon(polygon: Polygon, half_plane: AffineForm) -> Polygon:
    """Keep the closed side on which half_plane is nonnegative."""
    if not polygon:
        return ()
    result = []
    start = polygon[-1]
    start_value = half_plane.evaluate(start)
    for end in polygon:
        end_value = half_plane.evaluate(end)
        if start_value * end_value < 0:
            t = start_value / (start_value - end_value)
            x = start[0] + t * (end[0] - start[0])
            y = start[1] + t * (end[1] - start[1])
            result.append((x, y))
        if end_value >= 0:
            result.append(end)
        start, start_value = end, end_value
    return tuple(result)


def triangulate_convex(polygon: Polygon) -> tuple[Triangle, ...]:
    pieces = []
    for index in range(1, len(polygon) - 1):
        triangle = polygon[0], polygon[index], polygon[index + 1]
        if polygon_area(triangle):
            pieces.append(triangle)
    return tuple(pieces)

from dataclasses import dataclass
from fractions import Fraction

from calibration.geometry import AffineForm, Polygon, Triangle, clip_polygon, polygon_area, triangulate_convex
from calibration.range import FULL_SCALE_HIGH, FULL_SCALE_LOW, classify_clipping_band
from calibration.response import CalibratedScenario


@dataclass(frozen=True)
class SourcePiece:
    vertices: Triangle
    area_fraction: Fraction


def _clipping_regions(polygon: Polygon, form: AffineForm) -> tuple[Polygon, ...]:
    if not polygon:
        return ()
    readings = [form.evaluate(vertex) for vertex in polygon]
    # The same band at the extrema also handles an entire region on a limit.
    if classify_clipping_band(min(readings)) == classify_clipping_band(max(readings)):
        return (polygon,)
    low = clip_polygon(polygon, form.at_most(FULL_SCALE_LOW))
    middle = clip_polygon(polygon, form.at_least(FULL_SCALE_LOW))
    middle = clip_polygon(middle, form.at_most(FULL_SCALE_HIGH))
    high = clip_polygon(polygon, form.at_least(FULL_SCALE_HIGH))
    return tuple(region for region in (low, middle, high) if polygon_area(region))


def partition_scenario(model: CalibratedScenario) -> tuple[SourcePiece, ...]:
    source = model.scenario.vertices
    source_area = polygon_area(source)
    if not source_area:
        raise ValueError('源三角形须具有正面积')
    pieces = []
    for region_a in _clipping_regions(source, model.a):
        for region_ab in _clipping_regions(region_a, model.b):
            for triangle in triangulate_convex(region_ab):
                pieces.append(SourcePiece(triangle, polygon_area(triangle) / source_area))
    if sum((piece.area_fraction for piece in pieces), Fraction(0)) != 1:
        raise ValueError('限幅分区未保全源情景质量')
    return tuple(pieces)

from dataclasses import dataclass
from fractions import Fraction

from archive.observations import parse_pair, validate_label
from archive.rationals import encode_rational
from calibration.geometry import Triangle, polygon_area
from calibration.weights import validate_weights


@dataclass(frozen=True)
class Scenario:
    name: str
    vertices: Triangle
    weight: Fraction

    def as_input(self) -> dict:
        return {
            'name': self.name,
            'vertices': [[encode_rational(x), encode_rational(y)] for x, y in self.vertices],
            'weight': encode_rational(self.weight),
        }


def normalize_scenarios(values: object) -> tuple[Scenario, ...]:
    if not isinstance(values, (list, tuple)) or not values:
        raise ValueError('须提供至少一个带权情景')
    names = set()
    triangles = []
    raw_weights = []
    for item in values:
        if not isinstance(item, dict) or not {'name', 'vertices', 'weight'} <= item.keys():
            raise ValueError('情景缺少名称、顶点或权重')
        name = validate_label(item['name'], '情景名')
        if name in names:
            raise ValueError(f'重复情景 {name!r}')
        names.add(name)
        vertices = item['vertices']
        if not isinstance(vertices, (list, tuple)) or len(vertices) != 3:
            raise ValueError('源三角形须有三个顶点')
        first, second, third = sorted(parse_pair(vertex) for vertex in vertices)
        triangle = first, second, third
        if not polygon_area(triangle):
            raise ValueError('源三角形须具有正面积')
        triangles.append((name, triangle))
        raw_weights.append(item['weight'])
    weights = validate_weights(raw_weights)
    scenarios = (Scenario(name, vertices, weight) for (name, vertices), weight in zip(triangles, weights))
    return tuple(sorted(scenarios, key=lambda scenario: scenario.name))

from fractions import Fraction
from typing import Iterable

from archive.rationals import parse_rational


def validate_weights(values: Iterable[object]) -> tuple[Fraction, ...]:
    weights = tuple(parse_rational(value) for value in values)
    if any(weight < 0 for weight in weights):
        raise ValueError('情景权重须非负')
    if sum(weights, Fraction(0)) != 1:
        raise ValueError('情景权重总和须恰为 1')
    return weights

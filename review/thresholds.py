from dataclasses import dataclass
from fractions import Fraction

from archive.rationals import parse_rational
from calibration.geometry import AffineForm, polygon_area
from issue.pieces import EvidencePiece
from review.conditional import calculate_conditional, selected_region
from review.roots import HIGH_ROOT, LOW_ROOT, QuadraticRoot, compare_root, make_quadratic_root, rational_sqrt
from review.windows import ReviewWindow


_ZERO = Fraction(0)
_ONE = Fraction(1)


@dataclass(frozen=True)
class ThresholdOutcome:
    selected: Fraction
    threshold: Fraction | QuadraticRoot | None


def parse_minimum_rate(value: object) -> Fraction:
    rate = parse_rational(value)
    if not _ZERO <= rate <= _ONE:
        raise ValueError('通过率目标须落在闭量程内')
    return rate


def _channel(piece: EvidencePiece, index: int) -> AffineForm:
    first, second, third = (vertex[index] for vertex in piece.vertices)
    return AffineForm(second - first, third - first, first)


def _breakpoints(pieces: tuple[EvidencePiece, ...], window: ReviewWindow) -> list[Fraction]:
    """Second-channel values at which the joint mass can change its analytic form."""
    points = {_ZERO, _ONE}
    for piece in pieces:
        region = selected_region(piece, window)
        if not polygon_area(region):
            continue
        b = _channel(piece, 1)
        if b.u == 0 and b.v == 0:
            points.add(b.constant)
        else:
            for vertex in region:
                points.add(b.evaluate(vertex))
    return sorted(points)


def _interval_polynomial(pieces: tuple[EvidencePiece, ...], window: ReviewWindow,
                         low: Fraction, high: Fraction) -> tuple[Fraction, Fraction, Fraction]:
    """Quadratic coefficients of the joint mass on the open interval (low, high).

    No breakpoint lies inside the interval, so the joint mass is a single quadratic
    there; three exact samples determine it uniquely.
    """
    span = high - low
    samples = [low + span * offset / 4 for offset in (1, 2, 3)]
    y1, y2, y3 = (calculate_conditional(pieces, window, point).passed for point in samples)
    first, second, third = samples
    slope12 = (y2 - y1) / (second - first)
    slope23 = (y3 - y2) / (third - second)
    bend = (slope23 - slope12) / (third - first)
    linear = slope12 - bend * (first + second)
    constant = y1 - slope12 * first + bend * first * second
    return bend, linear, constant


def _crossing_root(a: Fraction, b: Fraction, c: Fraction, low: Fraction,
                   high: Fraction) -> Fraction | QuadraticRoot:
    """Root of a·t² + b·t + c inside (low, high), given a sign change across it."""
    if not a:
        if not b:
            raise AssertionError('常数多项式不可能在区间内变号')
        value = -c / b
        if not low < value < high:
            raise AssertionError('线性根不在预期区间内')
        return value
    discriminant = b * b - 4 * a * c
    root = rational_sqrt(discriminant)
    if root is not None:
        candidates = [(-b - root) / (2 * a), (-b + root) / (2 * a)]
        inside = [value for value in candidates if low < value < high]
        if len(inside) != 1:
            raise AssertionError('区间内的有理根不唯一')
        return inside[0]
    value = make_quadratic_root(a, b, c, LOW_ROOT if a > 0 else HIGH_ROOT)
    if compare_root(value, low) != 1 or compare_root(value, high) != -1:
        raise AssertionError('二次实根不在预期区间内')
    return value


def select_threshold(pieces: tuple[EvidencePiece, ...], window: ReviewWindow,
                     minimum_rate: Fraction) -> ThresholdOutcome:
    """Highest setting in [0, 1] whose conditional pass rate meets minimum_rate.

    The joint mass N(t) is nonincreasing and left-continuous in t, so the feasible
    settings form a closed interval [0, t*]; scanning the piecewise-quadratic pieces
    from the right locates t* exactly.
    """
    selected = calculate_conditional(pieces, window, _ZERO).selected
    if not selected:
        return ThresholdOutcome(selected, None)
    target = minimum_rate * selected
    points = _breakpoints(pieces, window)
    at_point = {point: calculate_conditional(pieces, window, point).passed for point in points}
    for index in range(len(points) - 2, -1, -1):
        low, high = points[index], points[index + 1]
        if index == len(points) - 2 and at_point[high] >= target:
            return ThresholdOutcome(selected, high)
        a, b, c = _interval_polynomial(pieces, window, low, high)
        if a * low * low + b * low + c > target:
            return ThresholdOutcome(selected, _crossing_root(a, b, c - target, low, high))
        if at_point[low] >= target:
            return ThresholdOutcome(selected, low)
    raise AssertionError('不可达：零处联合质量必不低于目标')

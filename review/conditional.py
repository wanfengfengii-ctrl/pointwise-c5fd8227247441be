from dataclasses import dataclass
from fractions import Fraction

from calibration.geometry import AffineForm, Triangle, clip_polygon, polygon_area
from issue.pieces import EvidencePiece
from review.windows import ReviewWindow


_ZERO = Fraction(0)
_ONE = Fraction(1)
REFERENCE_TRIANGLE: Triangle = ((_ZERO, _ZERO), (_ONE, _ZERO), (_ZERO, _ONE))
_REFERENCE_AREA = polygon_area(REFERENCE_TRIANGLE)


@dataclass(frozen=True)
class ConditionalMasses:
    selected: Fraction
    passed: Fraction
    rate: Fraction | None


def _channel(piece: EvidencePiece, index: int) -> AffineForm:
    first, second, third = (vertex[index] for vertex in piece.vertices)
    return AffineForm(second - first, third - first, first)


def measure_piece(piece: EvidencePiece, window: ReviewWindow, threshold: Fraction) -> tuple[Fraction, Fraction]:
    if window.empty:
        return _ZERO, _ZERO
    a = _channel(piece, 0)
    eligible = REFERENCE_TRIANGLE
    if a.u == 0 and a.v == 0:
        if not window.contains(a.constant):
            return _ZERO, _ZERO
    else:
        # For a nonconstant affine coordinate each endpoint is a null set in this domain.
        eligible = clip_polygon(eligible, a.at_least(window.low))
        eligible = clip_polygon(eligible, a.at_most(window.high))
    selected_area = polygon_area(eligible)
    if not selected_area:
        return _ZERO, _ZERO
    b = _channel(piece, 1)
    passed_area = polygon_area(clip_polygon(eligible, b.at_least(threshold)))
    density = piece.mass / _REFERENCE_AREA
    return selected_area * density, passed_area * density


def calculate_conditional(pieces: tuple[EvidencePiece, ...], window: ReviewWindow,
                          threshold: Fraction) -> ConditionalMasses:
    selected = _ZERO
    passed = _ZERO
    for piece in pieces:
        selected_part, passed_part = measure_piece(piece, window, threshold)
        selected += selected_part
        passed += passed_part
    return ConditionalMasses(selected, passed, passed / selected if selected else None)

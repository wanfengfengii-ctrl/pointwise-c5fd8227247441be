from dataclasses import dataclass
from fractions import Fraction

from calibration.geometry import Triangle
from calibration.range import FULL_SCALE_HIGH, FULL_SCALE_LOW


@dataclass(frozen=True)
class EvidencePiece:
    mass: Fraction
    vertices: Triangle


def validate_evidence(pieces: tuple[EvidencePiece, ...]) -> None:
    if not isinstance(pieces, tuple) or not pieces:
        raise ValueError('固定件须包含非空证据序列')
    total = Fraction(0)
    for piece in pieces:
        if not isinstance(piece, EvidencePiece) or not isinstance(piece.mass, Fraction) or piece.mass <= 0:
            raise ValueError('证据片须有正有理质量')
        if not isinstance(piece.vertices, tuple) or len(piece.vertices) != 3:
            raise ValueError('证据片须有三个有序输出顶点')
        for point in piece.vertices:
            if not isinstance(point, tuple) or len(point) != 2:
                raise ValueError('输出顶点须有甲乙两项')
            if any(not isinstance(value, Fraction) or not FULL_SCALE_LOW <= value <= FULL_SCALE_HIGH for value in point):
                raise ValueError('证据读值超出归一满量程或类型非法')
        total += piece.mass
    if total != 1:
        raise ValueError('固定件证据总质量须恰为 1')

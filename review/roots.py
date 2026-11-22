from dataclasses import dataclass
from fractions import Fraction
from math import gcd, isqrt, lcm

from archive.rationals import parse_rational


LOW_ROOT = 'low'
HIGH_ROOT = 'high'
_ROOT_NAMES = (LOW_ROOT, HIGH_ROOT)


def rational_sqrt(value: Fraction) -> Fraction | None:
    """Return the exact square root of a nonnegative rational, or None when irrational."""
    if value < 0:
        return None
    numerator = isqrt(value.numerator)
    denominator = isqrt(value.denominator)
    if numerator * numerator == value.numerator and denominator * denominator == value.denominator:
        return Fraction(numerator, denominator)
    return None


@dataclass(frozen=True)
class QuadraticRoot:
    """Irrational root of a·t² + b·t + c = 0, pinned down as the low or high real root."""
    a: Fraction
    b: Fraction
    c: Fraction
    root: str

    def __post_init__(self) -> None:
        if any(not isinstance(value, Fraction) for value in (self.a, self.b, self.c)):
            raise ValueError('二次系数须为有理数')
        if self.a <= 0:
            raise ValueError('二次项系数须为正')
        if self.root not in _ROOT_NAMES:
            raise ValueError('须指定低根或高根')
        discriminant = self.b * self.b - 4 * self.a * self.c
        if discriminant <= 0:
            raise ValueError('二次式须有两个相异实根')
        if rational_sqrt(discriminant) is not None:
            raise ValueError('二次实根须为无理数')


def make_quadratic_root(a: object, b: object, c: object, root: str) -> QuadraticRoot:
    """Build a normalized QuadraticRoot from rational coefficients and check its range."""
    a, b, c = (parse_rational(value) for value in (a, b, c))
    if not a:
        raise ValueError('二次项系数须非零')
    if root not in _ROOT_NAMES:
        raise ValueError('须指定低根或高根')
    scale = lcm(a.denominator, b.denominator, c.denominator)
    coeffs = [int(value * scale) for value in (a, b, c)]
    common = gcd(gcd(abs(coeffs[0]), abs(coeffs[1])), abs(coeffs[2]))
    coeffs = [value // common for value in coeffs]
    if coeffs[0] < 0:
        coeffs = [-value for value in coeffs]
    result = QuadraticRoot(Fraction(coeffs[0]), Fraction(coeffs[1]), Fraction(coeffs[2]), root)
    if compare_root(result, Fraction(0)) != 1 or compare_root(result, Fraction(1)) != -1:
        raise ValueError('二次实根须落在闭量程内')
    return result


def compare_root(root: QuadraticRoot, value: Fraction) -> int:
    """Return 1 when the root exceeds the rational value, -1 when it falls below.

    The root is irrational and the value rational, so the two are never equal.
    """
    if not isinstance(root, QuadraticRoot) or not isinstance(value, Fraction):
        raise ValueError('须以二次实根和有理值比较')
    residual = root.a * value * value + root.b * value + root.c
    vertex = -root.b / (2 * root.a)
    if root.root == LOW_ROOT:
        return 1 if (residual > 0 and value < vertex) else -1
    return -1 if (residual > 0 and value > vertex) else 1

from fractions import Fraction


def parse_rational(value: object) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if type(value) is int:
        return Fraction(value)
    if isinstance(value, str):
        try:
            return Fraction(value)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(f'非法有理数 {value!r}') from exc
    raise ValueError('有理数必须是整数、Fraction 或有理文本')


def encode_rational(value: Fraction) -> str:
    return str(parse_rational(value))

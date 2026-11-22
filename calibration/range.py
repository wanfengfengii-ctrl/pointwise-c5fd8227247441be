from fractions import Fraction


FULL_SCALE_LOW = Fraction(0)
FULL_SCALE_HIGH = Fraction(1)


def classify_clipping_band(value: Fraction) -> str:
    if value <= FULL_SCALE_LOW:
        return 'low'
    if value >= FULL_SCALE_HIGH:
        return 'high'
    return 'middle'


def clamp_reading(value: Fraction) -> Fraction:
    band = classify_clipping_band(value)
    if band == 'low':
        return FULL_SCALE_LOW
    if band == 'high':
        return FULL_SCALE_HIGH
    return value

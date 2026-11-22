from dataclasses import dataclass
from fractions import Fraction

from archive.rationals import parse_rational


@dataclass(frozen=True)
class ReviewWindow:
    low: Fraction
    high: Fraction
    include_low: bool
    include_high: bool

    def __post_init__(self) -> None:
        if not isinstance(self.low, Fraction) or not isinstance(self.high, Fraction):
            raise ValueError('窗口端点须为精确分数')
        if type(self.include_low) is not bool or type(self.include_high) is not bool:
            raise ValueError('两个窗口开闭标志须为布尔值')
        if self.low > self.high:
            raise ValueError('窗口左端不得大于右端')

    @property
    def empty(self) -> bool:
        return self.low == self.high and not (self.include_low and self.include_high)

    def contains(self, value: Fraction) -> bool:
        left = value > self.low or (value == self.low and self.include_low)
        right = value < self.high or (value == self.high and self.include_high)
        return left and right


def parse_window(value: object) -> ReviewWindow:
    if not isinstance(value, dict) or set(value) != {'low', 'high', 'include_low', 'include_high'}:
        raise ValueError('窗口须给出两个端点和两个开闭标志')
    return ReviewWindow(
        parse_rational(value['low']),
        parse_rational(value['high']),
        value['include_low'],
        value['include_high'],
    )


def parse_threshold(value: object) -> Fraction:
    return parse_rational(value)

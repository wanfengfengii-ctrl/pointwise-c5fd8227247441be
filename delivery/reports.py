from dataclasses import dataclass
from fractions import Fraction

from issue.packet import PacketRef
from review.roots import QuadraticRoot
from review.windows import ReviewWindow


@dataclass(frozen=True)
class ReportDraft:
    parent: PacketRef
    window: ReviewWindow
    threshold: Fraction
    selected: Fraction
    passed: Fraction
    rate: Fraction | None

    @property
    def status(self) -> str:
        return 'no_evidence' if self.rate is None else 'measured'


@dataclass(frozen=True)
class SignedReport:
    number: int
    draft: ReportDraft


def validate_report(draft: ReportDraft) -> None:
    if not isinstance(draft, ReportDraft) or not isinstance(draft.parent, PacketRef):
        raise ValueError('报告须保存实际父件')
    if not isinstance(draft.window, ReviewWindow):
        raise ValueError('报告须保存原窗口')
    if any(not isinstance(value, Fraction) for value in (draft.threshold, draft.selected, draft.passed)):
        raise ValueError('报告须保存有理门槛和质量')
    if not 0 <= draft.passed <= draft.selected <= 1:
        raise ValueError('报告质量须满足 0 ≤ 联合达标 ≤ 筛选 ≤ 1')
    if draft.window.empty and draft.selected != 0:
        raise ValueError('空窗口的筛选质量须为零')
    if draft.selected:
        if not isinstance(draft.rate, Fraction) or draft.rate != draft.passed / draft.selected:
            raise ValueError('条件通过率须与已签质量一致')
    elif draft.rate is not None:
        raise ValueError('无证据时条件通过率须为空')


@dataclass(frozen=True)
class ThresholdDraft:
    parent: PacketRef
    window: ReviewWindow
    minimum_rate: Fraction
    selected: Fraction
    threshold: Fraction | QuadraticRoot | None

    @property
    def status(self) -> str:
        return 'no_evidence' if self.threshold is None else 'measured'


@dataclass(frozen=True)
class SignedThresholdReport:
    number: int
    draft: ThresholdDraft


def validate_threshold_report(draft: ThresholdDraft) -> None:
    if not isinstance(draft, ThresholdDraft) or not isinstance(draft.parent, PacketRef):
        raise ValueError('报告须保存实际父件')
    if not isinstance(draft.window, ReviewWindow):
        raise ValueError('报告须保存原窗口')
    if not isinstance(draft.minimum_rate, Fraction) or not 0 <= draft.minimum_rate <= 1:
        raise ValueError('通过率目标须为闭量程内有理数')
    if not isinstance(draft.selected, Fraction) or not 0 <= draft.selected <= 1:
        raise ValueError('筛选质量须为闭量程内有理数')
    if draft.window.empty and draft.selected != 0:
        raise ValueError('空窗口的筛选质量须为零')
    threshold = draft.threshold
    if draft.selected:
        if isinstance(threshold, Fraction):
            if not 0 <= threshold <= 1:
                raise ValueError('门槛须落在闭量程内')
        elif not isinstance(threshold, QuadraticRoot):
            raise ValueError('有证据时门槛须为有理数或二次实根')
    elif threshold is not None:
        raise ValueError('无证据时门槛须为空')

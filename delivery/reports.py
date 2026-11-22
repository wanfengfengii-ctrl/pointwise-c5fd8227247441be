from dataclasses import dataclass
from fractions import Fraction

from issue.packet import PacketRef
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

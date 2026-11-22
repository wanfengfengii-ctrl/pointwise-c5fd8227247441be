from fractions import Fraction

from archive.rationals import parse_rational
from delivery.reports import SignedReport, SignedThresholdReport, validate_threshold_report
from delivery.transactions import ReportStore
from review.roots import compare_root


class ReportNotFound(LookupError):
    pass


def receive_report(store: ReportStore, number: int) -> SignedReport:
    report = store.read_signed(number)
    if report is None:
        raise ReportNotFound(f'未找到已签报告 {number}')
    store.record_receipt(report.number)
    return report


def receive_threshold_review(store: ReportStore, number: int) -> SignedThresholdReport:
    report = store.read_threshold(number)
    if report is None:
        raise ReportNotFound(f'未找到已签反查报告 {number}')
    store.record_threshold_receipt(report.number)
    return report


def threshold_allows(report: SignedThresholdReport, setting: object) -> bool | None:
    """Judge solely from a received inverse-lookup report whether setting ≤ signed threshold."""
    if not isinstance(report, SignedThresholdReport):
        raise ValueError('须凭已签反查报告核对设点')
    draft = report.draft
    validate_threshold_report(draft)
    value = parse_rational(setting)
    if not 0 <= value <= 1:
        raise ValueError('设点须落在闭量程内')
    threshold = draft.threshold
    if threshold is None:
        return None
    if isinstance(threshold, Fraction):
        return bool(value <= threshold)
    return compare_root(threshold, value) >= 0

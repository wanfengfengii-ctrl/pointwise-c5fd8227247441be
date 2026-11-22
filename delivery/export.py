from fractions import Fraction

from archive.rationals import encode_rational
from delivery.reports import SignedReport, SignedThresholdReport
from review.roots import QuadraticRoot


def export_handoff(report: SignedReport) -> dict:
    draft = report.draft
    window = draft.window
    return {
        'number': report.number,
        'parent': draft.parent.as_dict(),
        'window': {
            'low': encode_rational(window.low),
            'high': encode_rational(window.high),
            'include_low': window.include_low,
            'include_high': window.include_high,
        },
        'threshold': encode_rational(draft.threshold),
        'status': draft.status,
        'selected': encode_rational(draft.selected),
        'passed': encode_rational(draft.passed),
        'rate': None if draft.rate is None else encode_rational(draft.rate),
    }


def _threshold_payload(threshold: Fraction | QuadraticRoot | None) -> dict:
    if threshold is None:
        return {'kind': 'none'}
    if isinstance(threshold, Fraction):
        return {'kind': 'rational', 'value': encode_rational(threshold)}
    if isinstance(threshold, QuadraticRoot):
        return {
            'kind': 'quadratic',
            'a': encode_rational(threshold.a),
            'b': encode_rational(threshold.b),
            'c': encode_rational(threshold.c),
            'root': threshold.root,
        }
    raise ValueError('已签门槛类型非法')


def export_threshold_handoff(report: SignedThresholdReport) -> dict:
    draft = report.draft
    window = draft.window
    return {
        'number': report.number,
        'parent': draft.parent.as_dict(),
        'window': {
            'low': encode_rational(window.low),
            'high': encode_rational(window.high),
            'include_low': window.include_low,
            'include_high': window.include_high,
        },
        'minimum_rate': encode_rational(draft.minimum_rate),
        'selected': encode_rational(draft.selected),
        'status': draft.status,
        'threshold': _threshold_payload(draft.threshold),
    }

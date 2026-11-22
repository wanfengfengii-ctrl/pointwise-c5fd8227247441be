from archive.rationals import encode_rational
from delivery.reports import SignedReport


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

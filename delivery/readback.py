from delivery.reports import SignedReport
from delivery.transactions import ReportStore


class ReportNotFound(LookupError):
    pass


def receive_report(store: ReportStore, number: int) -> SignedReport:
    report = store.read_signed(number)
    if report is None:
        raise ReportNotFound(f'未找到已签报告 {number}')
    store.record_receipt(report.number)
    return report

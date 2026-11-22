from delivery.reports import ReportDraft, SignedReport
from delivery.transactions import ReportStore
from review.admission import admit_packet
from review.conditional import calculate_conditional
from review.windows import parse_threshold, parse_window


def submit_review(store: ReportStore, *, batch: str, packet_id: str, packet_text: str,
                  window: dict, threshold: object) -> SignedReport:
    bounds = parse_window(window)
    minimum = parse_threshold(threshold)
    packet = admit_packet(batch, packet_id, packet_text)
    masses = calculate_conditional(packet.pieces, bounds, minimum)
    draft = ReportDraft(packet.ref, bounds, minimum, masses.selected, masses.passed, masses.rate)
    return store.publish(draft)

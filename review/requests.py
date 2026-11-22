from delivery.reports import ReportDraft, SignedReport, SignedThresholdReport, ThresholdDraft
from delivery.transactions import ReportStore
from review.admission import admit_packet
from review.conditional import calculate_conditional
from review.thresholds import parse_minimum_rate, select_threshold
from review.windows import parse_threshold, parse_window


def submit_review(store: ReportStore, *, batch: str, packet_id: str, packet_text: str,
                  window: dict, threshold: object) -> SignedReport:
    bounds = parse_window(window)
    minimum = parse_threshold(threshold)
    packet = admit_packet(batch, packet_id, packet_text)
    masses = calculate_conditional(packet.pieces, bounds, minimum)
    draft = ReportDraft(packet.ref, bounds, minimum, masses.selected, masses.passed, masses.rate)
    return store.publish(draft)


def submit_threshold_review(store: ReportStore, *, batch: str, packet_id: str, packet_text: str,
                            window: dict, minimum_rate: object) -> SignedThresholdReport:
    bounds = parse_window(window)
    rate = parse_minimum_rate(minimum_rate)
    packet = admit_packet(batch, packet_id, packet_text)
    outcome = select_threshold(packet.pieces, bounds, rate)
    draft = ThresholdDraft(packet.ref, bounds, rate, outcome.selected, outcome.threshold)
    return store.publish_threshold(draft)

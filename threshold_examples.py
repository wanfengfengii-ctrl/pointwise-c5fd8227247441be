from contextlib import closing
from fractions import Fraction
import sqlite3

from archive.batches import BatchArchive
from archive.revisions import RevisionStore
from calibration.response import CalibrationStore
from delivery.transactions import ReportStore
from issue.catalog import IssueCatalog
from issue.packet import encode_packet
from issue.publication import issue_packet
from review.requests import submit_review


def scenario(name, a, b, weight=1):
    return {
        "name": name,
        "vertices": [[0, 0], [1, 0], [0, 1]],
        "weight": weight,
        "a": a,
        "b": b,
    }


def window(low, high, *, include_low=True, include_high=True):
    return {
        "low": low,
        "high": high,
        "include_low": include_low,
        "include_high": include_high,
    }


CALIBRATIONS = {
    "continuous": [scenario("ordinary", [0, 0, 1], [1, 0, 0])],
    "saturated": [scenario("saturation", [0, 0, 1], [2, 0, 0])],
    "plateau": [
        scenario("low", [0, 0, 1], [0, 0, "1/4"], "1/2"),
        scenario("high", [0, 0, 1], [0, 0, "3/4"], "1/2"),
    ],
    "two-roots": [scenario("narrow-scale", [0, 0, 1], ["1/4", 0, "1/4"])],
    "window-cut": [scenario("paired", [1, 0, 0], [0, 1, 0])],
}

FULL_SCALE = window(1, 1)
CUT_WINDOW = window("1/4", "1/2", include_high=False)
EMPTY_WINDOW = window(0, 1, include_high=False)

# Each check specifies a V1 threshold, then the expected selected mass and rate.
FORWARD_CASES = (
    ("continuous", FULL_SCALE, "29/100", "1", "5041/10000"),
    ("continuous", FULL_SCALE, "3/10", "1", "49/100"),
    ("continuous", EMPTY_WINDOW, "0", "0", None),
    ("saturated", FULL_SCALE, "1", "1", "1/4"),
    ("plateau", FULL_SCALE, "1/2", "1", "1/2"),
    ("plateau", FULL_SCALE, "3/4", "1", "1/2"),
    ("plateau", FULL_SCALE, "4/5", "1", "0"),
    ("two-roots", FULL_SCALE, "2/5", "1", "4/25"),
    ("window-cut", CUT_WINDOW, "5/8", "5/16", "1/20"),
)


def example_packets():
    """Issue the sample packets and return their references and texts after station closure."""
    issued = {}
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("PRAGMA foreign_keys = ON")
        revisions = RevisionStore(db)
        calibrations = CalibrationStore(db, revisions)
        catalog = IssueCatalog(db)
        for component in (revisions, calibrations, catalog):
            component.initialize()
        archive = BatchArchive(revisions)
        for batch, inputs in CALIBRATIONS.items():
            revision = archive.submit(batch, [{"name": "bench-01", "raw": [0, 0], "reference": [0, 0]}])
            model = calibrations.register(revision, inputs)
            packet = issue_packet(calibrations, catalog, batch=batch,
                                  calibration_id=model.number, version=model.version)
            issued[batch] = packet.ref, encode_packet(catalog.get(packet.ref.packet_id))
    return issued


def main():
    packets = example_packets()
    with closing(sqlite3.connect(":memory:")) as db:
        db.execute("PRAGMA foreign_keys = ON")
        store = ReportStore(db)
        store.initialize()
        for batch, bounds, threshold, selected, rate in FORWARD_CASES:
            ref, text = packets[batch]
            report = submit_review(store, batch=batch, packet_id=ref.packet_id,
                                   packet_text=text, window=bounds, threshold=threshold)
            expected_selected = Fraction(selected)
            expected_rate = None if rate is None else Fraction(rate)
            expected_passed = expected_selected * (expected_rate or Fraction(0))
            expected = (ref, expected_selected, expected_passed, expected_rate)
            draft = report.draft
            actual = (draft.parent, draft.selected, draft.passed, draft.rate)
            if actual != expected:
                raise AssertionError(f"{batch} at {threshold}: expected {expected}, got {actual}")
            print(f"{batch} B >= {threshold}: D={draft.selected} N={draft.passed} rate={draft.rate}")


if __name__ == "__main__":
    main()

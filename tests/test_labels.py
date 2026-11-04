"""P5.1: every signal, fact, segment and event type has a plain label."""

from typing import get_args

import pytest

from sis.api import labels
from sis.api.schemas import Segment
from sis.delta.diff import EVENT_TYPES
from sis.signals.catalogue import SIGNALS


def test_every_signal_has_a_label() -> None:
    assert {s.signal_id for s in SIGNALS} == set(labels.SIGNAL_LABELS)
    for s in SIGNALS:
        lab = labels.SIGNAL_LABELS[s.signal_id]
        assert lab.short and lab.one
        for v in (1.0, 3.0, 9.8, 800.0):  # every template formats for any value
            text = labels.signal_sentence(s.signal_id, v)
            assert text and "{" not in text and s.signal_id not in text


def test_every_fact_segment_event_has_a_label() -> None:
    assert set(labels.FACTS) == {s.fact for s in SIGNALS} - {"X"}
    assert set(labels.SEGMENTS) == set(get_args(Segment))
    assert set(labels.EVENT_SENTENCES) == set(EVENT_TYPES)
    for t in EVENT_TYPES:
        text = labels.event_sentence({"event_type": t, "subject": "D_waf",
                                      "from_value": "10.0", "to_value": "20.0"})
        assert text and "_" not in text, (t, text)


@pytest.mark.parametrize(("sid", "value", "details", "want"), [
    ("A_inferred_cves", 12, [], "12 known vulnerabilities inferred from software versions"),
    ("A_inferred_cves", 1, [], "1 known vulnerability inferred from software versions"),
    ("B_expired", 1, ["2026-01-01"], "A TLS certificate has expired"),
    ("C_admin_services", 3, [],
     "3 remote-admin or database services reachable from the internet"),
    ("D_waf", 1, ["Cloudflare (Cloudflare Inc.)", "Cloudflare (Cloudflare Inc.)"],
     "Behind Cloudflare (Cloudflare Inc.)"),
    ("D_waf", 1, [], "Behind a web application firewall"),
    ("D_hardening_headers", 1, ["strict-transport-security content-security-policy"],
     "Web responses set hardening headers: HSTS, CSP"),
    ("B_cert_age_days", 1100, [], "Oldest certificate was issued 3.0 years before the scan"),
    ("A_max_cvss", 9.8, [], "Worst known vulnerability scores 9.8 of 10 (CVSS)"),
])
def test_signal_sentence(sid: str, value: float, details: list[str], want: str) -> None:
    assert labels.signal_sentence(sid, value, details) == want


def test_event_sentences() -> None:
    def ev(t: str, s: str | None, f: str | None, to: str | None) -> str:
        return labels.event_sentence({"event_type": t, "subject": s, "from_value": f,
                                      "to_value": to})

    assert ev("protection_removed", "D_waf", "Cloudflare (Cloudflare Inc.)", None) == \
        "Protection by Cloudflare (Cloudflare Inc.) was removed"
    assert ev("protection_removed", "D_hardening_headers", "strict-transport-security", None) \
        == "Hardening headers removed (HSTS)"
    assert ev("segment_changed", "segment", "untouched", "displace") == \
        "Moved from Untouched to Has a vendor"
    assert ev("cert_expired_since", "B_expired", None, "2026-11-15") == \
        "A TLS certificate expired since the last delivery"
    assert ev("service_new", "1.2.3.4:22", None, "ssh") == "New ssh service answering"
    assert labels.event_subject({"event_type": "service_new", "subject": "1.2.3.4:22"}) == \
        "1.2.3.4:22"

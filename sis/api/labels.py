"""Plain-language labels for the UI (phase P5.1): signals, facts, segments, events.

Signal ids never reach a page outside the "Technical details" block; every place a signal is
named goes through `signal_short` (a few words) or `signal_sentence` (1 line with the value).
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SignalLabel:
    short: str  # a few words: the list page's "top reason", event sentences
    one: str  # sentence when the value is 1 (or the signal is a flag)
    many: str | None = None  # sentence when the value is not 1; {n} is the value as an integer
    detail: str | None = None  # sentence with {d}, the evidence values, when there are any


SIGNAL_LABELS: dict[str, SignalLabel] = {
    "A_fingerprinted": SignalLabel(
        "Software versions visible", "Software names and versions are visible to anyone"),
    "A_inferred_cves": SignalLabel(
        "Known vulnerabilities", "1 known vulnerability inferred from software versions",
        "{n:,} known vulnerabilities inferred from software versions"),
    "A_max_cvss": SignalLabel(
        "Severe vulnerability", "Worst known vulnerability scores {v:.1f} of 10 (CVSS)",
        "Worst known vulnerability scores {v:.1f} of 10 (CVSS)"),
    "A_eol": SignalLabel(
        "End-of-life software", "Runs a product or operating system past its end of life"),
    "A_os_leak": SignalLabel(
        "Operating system disclosed", "The operating system is disclosed to anyone",
        detail="The operating system is disclosed to anyone: {d}"),
    "A_cpe_per_header": SignalLabel(
        "Verbose web servers", "Web servers announce the software they run"),
    "B_self_signed": SignalLabel(
        "Self-signed certificate", "A self-signed TLS certificate is in use"),
    "B_expired": SignalLabel("Expired certificate", "A TLS certificate has expired"),
    "B_legacy_tls": SignalLabel("Legacy TLS", "Legacy TLS or SSLv3 is still offered"),
    "B_cert_age_days": SignalLabel(
        "Old certificate", "Oldest certificate was issued 1 day before the scan",
        "Oldest certificate was issued {age} before the scan"),
    "C_admin_services": SignalLabel(
        "Remote admin exposed",
        "1 remote-admin or database service reachable from the internet",
        "{n:,} remote-admin or database services reachable from the internet"),
    "C_windows_internals": SignalLabel(
        "Windows internals exposed", "Windows internals (NTLM or the Windows OS) are visible"),
    "C_asset_tags": SignalLabel(
        "Sensitive asset exposed",
        "A sensitive asset class is exposed (database, IoT, ICS, medical, devops or open "
        "directory)",
        "{n:,} sensitive asset classes are exposed (database, IoT, ICS, medical, devops or "
        "open directory)"),
    "C_breadth_modules": SignalLabel(
        "Many services", "1 kind of service answers", "{n:,} kinds of service answer"),
    "C_breadth_ports": SignalLabel("Many open ports", "1 open port", "{n:,} open ports"),
    "C_components_vs_peers": SignalLabel(
        "Large web stack", "1 web component on a single site",
        "Up to {n:,} web components on a single site"),
    "C_live_web": SignalLabel("Live website", "A live web service answers"),
    "C_any_service": SignalLabel("Service answering", "At least 1 of their services answered"),
    "D_waf": SignalLabel(
        "Web application firewall", "Behind a web application firewall",
        detail="Behind {d}"),
    "D_edge_substitute": SignalLabel(
        "CDN edge", "Fronted by a CDN edge (partial cover)",
        detail="Fronted by the {d} CDN edge (partial cover)"),
    "D_security_appliance": SignalLabel(
        "Security appliance", "A security appliance is in place",
        detail="Security appliance in place: {d}"),
    "D_vpn": SignalLabel(
        "VPN gateway", "A VPN gateway is in place", detail="VPN gateway in place: {d}"),
    "D_hardening_headers": SignalLabel(
        "Hardening headers", "Web responses set hardening headers",
        detail="Web responses set hardening headers: {d}"),
    "X_small_cloud": SignalLabel(
        "Small cloud provider", "Hosted on a small cloud provider",
        detail="Hosted on a small cloud provider: {d}"),
}

HEADER_NAMES = {"strict-transport-security": "HSTS", "content-security-policy": "CSP"}

FACTS: dict[str, tuple[str, str]] = {  # fact -> (name, what it means)
    "A": ("Visibly old software", "Outdated or vulnerable software that anyone can identify."),
    "B": ("Neglected certificates", "Expired, self-signed, old or legacy-TLS certificates."),
    "C": ("Exposed surface", "Services, ports and admin interfaces reachable from the internet."),
    "D": ("Protection present", "Security products or edge protection already in front."),
}

SEGMENTS: dict[str, tuple[str, str, str]] = {  # segment -> (name, 1 line, chip name)
    "untouched": ("Untouched", "Exposed, with no security product in sight", "Untouched"),
    "partially_covered": ("Partially covered",
                          "An edge platform, VPN or hardening headers, no security product",
                          "Partially covered"),
    "displace": ("Has a vendor", "A security vendor is already in place", "Has a vendor"),
    "low_surface": ("Low visible surface", "Nothing of theirs answered the scan", "Low surface"),
}

SEVERITY = {3: "High", 2: "Medium", 1: "Low"}


def _age(days: float) -> str:
    d = int(days)
    if d >= 730:
        return f"{d / 365.25:.1f} years"
    return f"{d:,} days"


def _details(signal_id: str, values: Sequence[str]) -> str:
    seen: list[str] = []
    for v in values:
        for part in (v.split() if signal_id == "D_hardening_headers" else [v]):
            part = HEADER_NAMES.get(part, part).strip()
            if part and part not in seen:
                seen.append(part)
    shown = ", ".join(seen[:3])
    return shown + (f" and {len(seen) - 3} more" if len(seen) > 3 else "")


def signal_short(signal_id: str) -> str:
    lab = SIGNAL_LABELS.get(signal_id)
    return lab.short if lab else signal_id


def signal_sentence(signal_id: str, value: float | None = None,
                    details: Sequence[str] = ()) -> str:
    """1 plain line for a signal, with its value (and, for D and X, the vendor) filled in."""
    lab = SIGNAL_LABELS.get(signal_id)
    if lab is None:
        return signal_id
    d = _details(signal_id, [x for x in details if x])
    if lab.detail and d:
        return lab.detail.format(d=d)
    if lab.many is None or value is None or value == 1:
        return lab.one.format(v=value or 0)
    return lab.many.format(n=int(value), v=value, age=_age(value))


def segment_name(segment: str | None) -> str:
    return SEGMENTS[segment][0] if segment in SEGMENTS else (segment or "")


def _protection(subject: str | None, value: str | None, verb: str) -> str:
    d = _details(subject or "", [value] if value else [])
    if subject in ("D_waf", "D_edge_substitute", "D_security_appliance", "D_vpn") and d:
        return f"Protection by {d} was {verb}"
    return f"{signal_short(subject or '')} {verb}" + (f" ({d})" if d else "")


EVENT_SENTENCES: dict[str, Callable[[str | None, str | None, str | None], str]] = {
    "entity_new": lambda s, f, t: "First seen in this delivery",
    "entity_gone": lambda s, f, t: "No longer seen in this delivery",
    "service_new": lambda s, f, t: f"New {t or 'service'} service answering",
    "service_gone": lambda s, f, t: f"The {f or 'service'} service stopped answering",
    "signal_appeared": lambda s, f, t: f"New since the last delivery: {signal_short(s or '')}",
    "signal_cleared": lambda s, f, t: f"No longer seen: {signal_short(s or '')}",
    "cert_expired_since": lambda s, f, t: "A TLS certificate expired since the last delivery",
    "protection_removed": lambda s, f, t: _protection(s, f, "removed"),
    "protection_added": lambda s, f, t: _protection(s, t, "added"),
    "exposure_up": lambda s, f, t: f"Exposure rose from {f} to {t}",
    "exposure_down": lambda s, f, t: f"Exposure fell from {f} to {t}",
    "segment_changed": lambda s, f, t: f"Moved from {segment_name(f)} to {segment_name(t)}",
}


def event_sentence(e: Any) -> str:
    """1 plain line for an event (an Event model or a dict with the same fields)."""
    get = e.get if isinstance(e, dict) else lambda k: getattr(e, k)
    fn = EVENT_SENTENCES.get(str(get("event_type")))
    if fn is None:
        return str(get("event_type"))
    return fn(get("subject"), get("from_value"), get("to_value"))


def event_subject(e: Any) -> str:
    """The subject worth showing beside the sentence: an ip:port, else nothing."""
    get = e.get if isinstance(e, dict) else lambda k: getattr(e, k)
    return str(get("subject")) if get("event_type") in ("service_new", "service_gone") else ""

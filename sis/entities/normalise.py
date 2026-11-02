"""Name hygiene for entity keys. Pure; no network (tldextract uses its bundled suffix list)."""

import ipaddress
import re

import tldextract

_EXTRACT = tldextract.TLDExtract(cache_dir=None, suffix_list_urls=())
_BAD_CHARS = re.compile(r"[\s/@:*,;\"'<>\\]")


def _is_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s.strip("[]"))
    except ValueError:
        return False
    return True


def normalise_name(s: str | None) -> str | None:
    """Lowercase, drop trailing dots and a leading `www.`; None unless it is a dotted,
    non-IP host name (DATA_MODEL.md 2.1 rule 1). A numeric last label is never a TLD, so
    partial IPs and version strings ('74.18.178', '1.0') are rejected too."""
    if s is None:
        return None
    n = s.strip().lower().rstrip(".")
    if n.startswith("www."):
        n = n[4:]
    if "." not in n or ".." in n or n.startswith(".") or _BAD_CHARS.search(n) or _is_ip(n):
        return None
    if n.rsplit(".", 1)[1].isdigit():
        return None
    return n


def registered_domain(s: str | None) -> str | None:
    """The public-suffix-aware base domain: 'a.b.example.co.uk' -> 'example.co.uk'.
    A leading wildcard label is dropped first. None when there is no registrable domain."""
    if s is None:
        return None
    s = s.strip()
    if s.startswith("*."):
        s = s[2:]
    n = normalise_name(s)
    if n is None:
        return None
    ext = _EXTRACT(n)
    if not ext.domain or not ext.suffix:
        return None
    return f"{ext.domain}.{ext.suffix}"


def host_registered_domain(host: str | None) -> str | None:
    """registered_domain of an HTTP Host value, which may carry a port. IP literals give None."""
    if host is None:
        return None
    h = host.strip()
    if h.startswith("["):  # bracketed IPv6
        return None
    if h.count(":") == 1:
        h = h.split(":", 1)[0]
    return registered_domain(h)

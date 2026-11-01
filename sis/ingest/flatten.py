"""Banner record -> flat Parquet row. The explorer's flattener (findings/queries/01_flatten.py)
moved into the package: same 93 columns, plus file_id. Nothing here touches the filesystem."""

import json
import re
from datetime import datetime
from typing import Any

import pyarrow as pa

HANDLED = {
    "data", "opts", "port", "hostnames", "domains", "timestamp", "location", "org", "isp",
    "os", "_shodan", "hash", "transport", "asn", "ip", "ip_str", "tags", "link", "http",
    "ssl", "cloud", "cpe", "cpe23", "cpe23_hash", "product", "version", "vulns", "uptime",
    "ipv6", "devicetype", "info", "device", "vendor", "mac", "tcp", "udp",
}
DROP_FROM_EXTRA = {"html", "screenshot"}  # bulky payloads, lengths kept instead
NOT_PROTOCOL = HANDLED - {"http", "ssl", "cloud", "vulns"}
SAN_RE = re.compile(r"\\x82.([A-Za-z0-9*_.-]+\.[A-Za-z]{2,})")

S, INT, F, B, T = pa.string(), pa.int64(), pa.float64(), pa.bool_(), pa.timestamp("us")
LS = pa.list_(pa.string())
SCHEMA = pa.schema([
    ("id", S), ("module", S), ("shodan_region", S), ("crawler", S), ("ptr", B),
    ("timestamp", T), ("port", INT), ("transport", S), ("ip_str", S), ("ipv6", S),
    ("org", S), ("isp", S), ("asn", S), ("os", S), ("link", S), ("product", S),
    ("version", S), ("info", S), ("uptime", INT), ("devicetype", S), ("device", S),
    ("vendor", S), ("hash", INT), ("hostnames", LS), ("domains", LS), ("tags", LS),
    ("cpe23", LS), ("vuln_ids", LS), ("n_vulns", INT), ("max_cvss", F), ("max_epss", F),
    ("opts_heartbleed", S), ("opts_vulns", LS),
    ("country_code", S), ("country_name", S), ("city", S), ("region_code", S),
    ("latitude", F), ("longitude", F),
    ("http_status", INT), ("http_title", S), ("http_server", S), ("http_waf", S),
    ("http_host", S), ("http_location", S), ("http_html_hash", INT), ("http_headers_hash", INT),
    ("http_components_hash", INT), ("http_dom_hash", INT), ("http_title_hash", INT),
    ("http_favicon_hash", INT), ("http_securitytxt", B), ("http_robots", B),
    ("http_sitemap", B), ("http_redirects", INT), ("http_html_len", INT),
    ("http_components", LS), ("http_component_cats", LS), ("http_header_names", LS),
    ("http_headers", S), ("http_identifiers", S),
    ("ssl_version", S), ("ssl_cipher", S), ("ssl_cipher_bits", INT),
    ("cert_issued", T), ("cert_expires", T), ("cert_expired", B), ("cert_subject_cn", S),
    ("cert_subject_o", S), ("cert_issuer_cn", S), ("cert_issuer_o", S),
    ("cert_self_signed", B), ("cert_pubkey_type", S), ("cert_pubkey_bits", INT),
    ("cert_sig_alg", S), ("cert_sha256", S), ("cert_san", LS), ("jarm", S), ("ja3s", S),
    ("trust_revoked", B), ("trust_browser", S), ("ssl_chain_len", INT), ("ssl_versions", LS),
    ("ssl_alpn", LS),
    ("cloud_provider", S), ("cloud_region", S), ("cloud_service", S),
    ("data", S), ("data_len", INT), ("html_len", INT), ("blocks", LS), ("extra_json", S),
    ("record_bytes", INT), ("file_id", S),
])
VSCHEMA = pa.schema([
    ("id", S), ("module", S), ("cve", S), ("cvss", F), ("cvss_version", F), ("cvss_v2", F),
    ("epss", F), ("ranking_epss", F), ("verified", B), ("kev", B), ("n_references", INT),
    ("summary", S), ("other_keys", S), ("file_id", S),
])


def num(v: Any, t: Any) -> Any:
    if v is None or isinstance(v, bool):
        return None
    try:
        return t(v)
    except (TypeError, ValueError):
        return None


def strs(v: Any) -> list[str] | None:
    if v is None:
        return None
    if isinstance(v, list):
        return [x if isinstance(x, str) else json.dumps(x) for x in v]
    return [str(v)]


def s(v: Any) -> str | None:
    if v is None:
        return None
    return v if isinstance(v, str) else json.dumps(v, default=str)


def certtime(v: Any) -> datetime | None:
    try:
        return datetime.strptime(v, "%Y%m%d%H%M%SZ")
    except (TypeError, ValueError):
        return None


def _dict(parent: dict[str, Any], key: str) -> dict[str, Any]:
    """parent[key] when it is an object, else an empty dict."""
    v = parent.get(key)
    return v if isinstance(v, dict) else {}


class MissingIdError(ValueError):
    """The record has no usable _shodan.id; it cannot be keyed, so it is dropped."""


class NotAnObjectError(ValueError):
    """The line is valid JSON but not an object."""


def flatten_record(obj: Any, file_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """One parsed banner -> (banner row, child vuln rows). Pure. Raises on records we drop."""
    if not isinstance(obj, dict):
        raise NotAnObjectError(type(obj).__name__)
    r: dict[str, Any] = obj
    vrows: list[dict[str, Any]] = []
    sh = r.get("_shodan") or {}
    loc = r.get("location") or {}
    http = r.get("http") or {}
    ssl = r.get("ssl") or {}
    cert = ssl.get("cert") or {}
    cloud = r.get("cloud") or {}
    opts = r.get("opts") or {}
    vulns = _dict(r, "vulns")
    rid, module = sh.get("id"), sh.get("module")
    if not isinstance(rid, str) or not rid:
        raise MissingIdError("record has no string _shodan.id")

    cvss, epss = [], []
    for cve, v in vulns.items():
        v = v if isinstance(v, dict) else {}
        cvss.append(num(v.get("cvss"), float))
        epss.append(num(v.get("epss"), float))
        other = {k: v[k] for k in v if k not in (
            "cvss", "cvss_version", "cvss_v2", "epss", "ranking_epss", "verified", "kev",
            "references", "summary")}
        vrows.append({
            "id": rid, "module": module, "cve": cve, "cvss": num(v.get("cvss"), float),
            "cvss_version": num(v.get("cvss_version"), float),
            "cvss_v2": num(v.get("cvss_v2"), float), "epss": num(v.get("epss"), float),
            "ranking_epss": num(v.get("ranking_epss"), float),
            "verified": v.get("verified") if isinstance(v.get("verified"), bool) else None,
            "kev": v.get("kev") if isinstance(v.get("kev"), bool) else None,
            "n_references": len(v.get("references") or []),
            "summary": (s(v.get("summary")) or "")[:500] or None,
            "other_keys": json.dumps(other, default=str) if other else None,
            "file_id": file_id,
        })
    cvss = [x for x in cvss if x is not None]
    epss = [x for x in epss if x is not None]

    comps = _dict(http, "components")
    cats = sorted({c for v in comps.values() if isinstance(v, dict)
                   for c in (v.get("categories") or [])})
    headers = _dict(http, "headers") if isinstance(http.get("headers"), dict) else None
    subj = _dict(cert, "subject")
    iss = _dict(cert, "issuer")
    cipher = _dict(ssl, "cipher")
    pub = _dict(cert, "pubkey")
    trust = _dict(ssl, "trust")
    san = []
    for e in cert.get("extensions") or []:
        if isinstance(e, dict) and e.get("name") == "subjectAltName":
            san = SAN_RE.findall(str(e.get("data")))
    data = r.get("data")
    data = data if isinstance(data, str) else s(data)
    extra = {k: v for k, v in r.items() if k not in HANDLED and k not in DROP_FROM_EXTRA}
    extra_s = json.dumps(extra, default=str) if extra else None
    html_top = r.get("html")
    fav = _dict(http, "favicon")

    row = {
        "id": rid, "module": module, "shodan_region": sh.get("region"),
        "crawler": sh.get("crawler"),
        "ptr": sh.get("ptr") if isinstance(sh.get("ptr"), bool) else None,
        "timestamp": r.get("timestamp"), "port": num(r.get("port"), int),
        "transport": r.get("transport"), "ip_str": r.get("ip_str"), "ipv6": s(r.get("ipv6")),
        "org": s(r.get("org")), "isp": s(r.get("isp")), "asn": s(r.get("asn")),
        "os": s(r.get("os")),
        "link": s(r.get("link")), "product": s(r.get("product")), "version": s(r.get("version")),
        "info": s(r.get("info")), "uptime": num(r.get("uptime"), int),
        "devicetype": s(r.get("devicetype")), "device": s(r.get("device")),
        "vendor": s(r.get("vendor")), "hash": num(r.get("hash"), int),
        "hostnames": strs(r.get("hostnames")), "domains": strs(r.get("domains")),
        "tags": strs(r.get("tags")), "cpe23": strs(r.get("cpe23")),
        "vuln_ids": list(vulns.keys()) if "vulns" in r else None,
        "n_vulns": len(vulns) if "vulns" in r else None,
        "max_cvss": max(cvss) if cvss else None, "max_epss": max(epss) if epss else None,
        "opts_heartbleed": s(opts.get("heartbleed")), "opts_vulns": strs(opts.get("vulns")),
        "country_code": loc.get("country_code"), "country_name": loc.get("country_name"),
        "city": s(loc.get("city")), "region_code": s(loc.get("region_code")),
        "latitude": num(loc.get("latitude"), float), "longitude": num(loc.get("longitude"), float),
        "http_status": num(http.get("status"), int), "http_title": s(http.get("title")),
        "http_server": s(http.get("server")), "http_waf": s(http.get("waf")),
        "http_host": s(http.get("host")), "http_location": s(http.get("location")),
        "http_html_hash": num(http.get("html_hash"), int),
        "http_headers_hash": num(http.get("headers_hash"), int),
        "http_components_hash": num(http.get("components_hash"), int),
        "http_dom_hash": num(http.get("dom_hash"), int),
        "http_title_hash": num(http.get("title_hash"), int),
        "http_favicon_hash": num(fav.get("hash"), int),
        "http_securitytxt": (http.get("securitytxt") is not None) if http else None,
        "http_robots": (http.get("robots") is not None) if http else None,
        "http_sitemap": (http.get("sitemap") is not None) if http else None,
        "http_redirects": len(http.get("redirects") or []) if http else None,
        "http_html_len": len(http["html"]) if isinstance(http.get("html"), str) else None,
        "http_components": sorted(comps.keys()) if http else None,
        "http_component_cats": cats if http else None,
        "http_header_names": sorted(k.lower() for k in headers) if headers is not None else None,
        "http_headers": json.dumps(headers) if headers is not None else None,
        "http_identifiers": s(http.get("identifiers")),
        "ssl_version": s(cipher.get("version")), "ssl_cipher": s(cipher.get("name")),
        "ssl_cipher_bits": num(cipher.get("bits"), int),
        "cert_issued": certtime(cert.get("issued")), "cert_expires": certtime(cert.get("expires")),
        "cert_expired": cert.get("expired") if isinstance(cert.get("expired"), bool) else None,
        "cert_subject_cn": s(subj.get("CN")), "cert_subject_o": s(subj.get("O")),
        "cert_issuer_cn": s(iss.get("CN")), "cert_issuer_o": s(iss.get("O")),
        "cert_self_signed": (subj == iss) if cert else None,
        "cert_pubkey_type": s(pub.get("type")), "cert_pubkey_bits": num(pub.get("bits"), int),
        "cert_sig_alg": s(cert.get("sig_alg")),
        "cert_sha256": s((cert.get("fingerprint") or {}).get("sha256")) if cert else None,
        "cert_san": san if cert else None,
        "jarm": s(ssl.get("jarm")), "ja3s": s(ssl.get("ja3s")),
        "trust_revoked": trust.get("revoked") if isinstance(trust.get("revoked"), bool) else None,
        "trust_browser": s(trust.get("browser")),
        "ssl_chain_len": len(ssl.get("chain") or []) if ssl else None,
        "ssl_versions": strs(ssl.get("versions")) if ssl else None,
        "ssl_alpn": strs(ssl.get("alpn")) if ssl else None,
        "cloud_provider": s(cloud.get("provider")), "cloud_region": s(cloud.get("region")),
        "cloud_service": s(cloud.get("service")),
        "data": data[:2000] if data else data, "data_len": len(data) if data is not None else None,
        "html_len": len(html_top) if isinstance(html_top, str) else None,
        "blocks": sorted(k for k in r if k not in NOT_PROTOCOL),
        "extra_json": extra_s,
        "record_bytes": 0,
    }
    row["file_id"] = file_id
    return row, vrows

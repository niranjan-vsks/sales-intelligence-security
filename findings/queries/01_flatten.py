"""Streaming flattener: Shodan banner JSONL -> Parquet (EXPLORATION.md 1b, 1c).

Usage:
  zstd -dc --long=31 FILE | python -I 01_flatten.py OUT_DIR [workers]
  python -I 01_flatten.py OUT_DIR [workers] < sample1m.jsonl

Writes OUT_DIR/banners/part-NNNNN.parquet, OUT_DIR/vulns/part-NNNNN.parquet
and OUT_DIR/stats.json (newline count, parsed rows, parse errors, key inventories).
The main process only cuts the byte stream at newlines; workers parse.
"""
import json
import re
import sys
import time
import threading
from collections import Counter
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path

import orjson
import pyarrow as pa
import pyarrow.parquet as pq

BLOCK = 96 * 1024 * 1024

HANDLED = {
    "data", "opts", "port", "hostnames", "domains", "timestamp", "location", "org", "isp",
    "os", "_shodan", "hash", "transport", "asn", "ip", "ip_str", "tags", "link", "http",
    "ssl", "cloud", "cpe", "cpe23", "cpe23_hash", "product", "version", "vulns", "uptime",
    "ipv6", "devicetype", "info", "device", "vendor", "mac", "tcp", "udp",
}
DROP_FROM_EXTRA = {"html", "screenshot"}  # bulky payloads, lengths kept instead
NOT_PROTOCOL = HANDLED - {"http", "ssl", "cloud", "vulns"}
SAN_RE = re.compile(r"\\x82.([A-Za-z0-9*_.-]+\.[A-Za-z]{2,})")

S, I, F, B, T = pa.string(), pa.int64(), pa.float64(), pa.bool_(), pa.timestamp("us")
LS = pa.list_(pa.string())
SCHEMA = pa.schema([
    ("id", S), ("module", S), ("shodan_region", S), ("crawler", S), ("ptr", B),
    ("timestamp", T), ("port", I), ("transport", S), ("ip_str", S), ("ipv6", S),
    ("org", S), ("isp", S), ("asn", S), ("os", S), ("link", S), ("product", S),
    ("version", S), ("info", S), ("uptime", I), ("devicetype", S), ("device", S),
    ("vendor", S), ("hash", I), ("hostnames", LS), ("domains", LS), ("tags", LS),
    ("cpe23", LS), ("vuln_ids", LS), ("n_vulns", I), ("max_cvss", F), ("max_epss", F),
    ("opts_heartbleed", S), ("opts_vulns", LS),
    ("country_code", S), ("country_name", S), ("city", S), ("region_code", S),
    ("latitude", F), ("longitude", F),
    ("http_status", I), ("http_title", S), ("http_server", S), ("http_waf", S),
    ("http_host", S), ("http_location", S), ("http_html_hash", I), ("http_headers_hash", I),
    ("http_components_hash", I), ("http_dom_hash", I), ("http_title_hash", I),
    ("http_favicon_hash", I), ("http_securitytxt", B), ("http_robots", B),
    ("http_sitemap", B), ("http_redirects", I), ("http_html_len", I),
    ("http_components", LS), ("http_component_cats", LS), ("http_header_names", LS),
    ("http_headers", S), ("http_identifiers", S),
    ("ssl_version", S), ("ssl_cipher", S), ("ssl_cipher_bits", I),
    ("cert_issued", T), ("cert_expires", T), ("cert_expired", B), ("cert_subject_cn", S),
    ("cert_subject_o", S), ("cert_issuer_cn", S), ("cert_issuer_o", S),
    ("cert_self_signed", B), ("cert_pubkey_type", S), ("cert_pubkey_bits", I),
    ("cert_sig_alg", S), ("cert_sha256", S), ("cert_san", LS), ("jarm", S), ("ja3s", S),
    ("trust_revoked", B), ("trust_browser", S), ("ssl_chain_len", I), ("ssl_versions", LS),
    ("ssl_alpn", LS),
    ("cloud_provider", S), ("cloud_region", S), ("cloud_service", S),
    ("data", S), ("data_len", I), ("html_len", I), ("blocks", LS), ("extra_json", S),
    ("record_bytes", I),
])
VSCHEMA = pa.schema([
    ("id", S), ("module", S), ("cve", S), ("cvss", F), ("cvss_version", F), ("cvss_v2", F),
    ("epss", F), ("ranking_epss", F), ("verified", B), ("kev", B), ("n_references", I),
    ("summary", S), ("other_keys", S),
])


def num(v, t):
    if v is None or isinstance(v, bool):
        return None
    try:
        return t(v)
    except (TypeError, ValueError):
        return None


def strs(v):
    if v is None:
        return None
    if isinstance(v, list):
        return [x if isinstance(x, str) else json.dumps(x) for x in v]
    return [str(v)]


def s(v):
    if v is None:
        return None
    return v if isinstance(v, str) else json.dumps(v, default=str)


def certtime(v):
    try:
        return datetime.strptime(v, "%Y%m%d%H%M%SZ")
    except (TypeError, ValueError):
        return None


def flatten(r, vrows, vkeys):
    sh = r.get("_shodan") or {}
    loc = r.get("location") or {}
    http = r.get("http") or {}
    ssl = r.get("ssl") or {}
    cert = ssl.get("cert") or {}
    cloud = r.get("cloud") or {}
    opts = r.get("opts") or {}
    vulns = r.get("vulns") if isinstance(r.get("vulns"), dict) else {}
    rid, module = sh.get("id"), sh.get("module")

    cvss, epss = [], []
    for cve, v in vulns.items():
        v = v if isinstance(v, dict) else {}
        vkeys.update(v.keys())
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
        })
    cvss = [x for x in cvss if x is not None]
    epss = [x for x in epss if x is not None]

    comps = http.get("components") if isinstance(http.get("components"), dict) else {}
    cats = sorted({c for v in comps.values() if isinstance(v, dict)
                   for c in (v.get("categories") or [])})
    headers = http.get("headers") if isinstance(http.get("headers"), dict) else None
    subj = cert.get("subject") if isinstance(cert.get("subject"), dict) else {}
    iss = cert.get("issuer") if isinstance(cert.get("issuer"), dict) else {}
    cipher = ssl.get("cipher") if isinstance(ssl.get("cipher"), dict) else {}
    pub = cert.get("pubkey") if isinstance(cert.get("pubkey"), dict) else {}
    trust = ssl.get("trust") if isinstance(ssl.get("trust"), dict) else {}
    san = []
    for e in cert.get("extensions") or []:
        if isinstance(e, dict) and e.get("name") == "subjectAltName":
            san = SAN_RE.findall(str(e.get("data")))
    data = r.get("data")
    data = data if isinstance(data, str) else s(data)
    extra = {k: v for k, v in r.items() if k not in HANDLED and k not in DROP_FROM_EXTRA}
    extra_s = json.dumps(extra, default=str) if extra else None
    html_top = r.get("html")
    fav = http.get("favicon") if isinstance(http.get("favicon"), dict) else {}

    return {
        "id": rid, "module": module, "shodan_region": sh.get("region"),
        "crawler": sh.get("crawler"), "ptr": sh.get("ptr") if isinstance(sh.get("ptr"), bool) else None,
        "timestamp": r.get("timestamp"), "port": num(r.get("port"), int),
        "transport": r.get("transport"), "ip_str": r.get("ip_str"), "ipv6": s(r.get("ipv6")),
        "org": s(r.get("org")), "isp": s(r.get("isp")), "asn": s(r.get("asn")), "os": s(r.get("os")),
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


def work(args):
    idx, buf, out = args
    rows, vrows = [], []
    stats = {"lines": buf.count(b"\n"), "rows": 0, "errors": 0, "error_examples": [],
             "top_keys": Counter(), "vuln_keys": Counter(), "modules": Counter(),
             "ts_min": None, "ts_max": None}
    for line in buf.split(b"\n"):
        if not line.strip():
            continue
        try:
            r = orjson.loads(line)
            row = flatten(r, vrows, stats["vuln_keys"])
        except Exception as e:  # record, never drop silently
            stats["errors"] += 1
            if len(stats["error_examples"]) < 3:
                stats["error_examples"].append(f"{type(e).__name__}: {e} :: {line[:200]!r}")
            continue
        row["record_bytes"] = len(line)
        stats["top_keys"].update(r.keys())
        stats["modules"][row["module"]] += 1
        rows.append(row)
    rows.sort(key=lambda x: x["module"] or "")
    ts = [x["timestamp"] for x in rows if x["timestamp"]]
    if ts:
        stats["ts_min"], stats["ts_max"] = min(ts), max(ts)
    tbl = pa.Table.from_pylist(
        [{**x, "timestamp": None} for x in rows],
        schema=SCHEMA,
    )
    tsa = pa.array([x["timestamp"] for x in rows], pa.string()).cast(T)
    tbl = tbl.set_column(SCHEMA.get_field_index("timestamp"), "timestamp", tsa)
    pq.write_table(tbl, f"{out}/banners/part-{idx:05d}.parquet", compression="zstd",
                   row_group_size=100_000)
    if vrows:
        pq.write_table(pa.Table.from_pylist(vrows, schema=VSCHEMA),
                       f"{out}/vulns/part-{idx:05d}.parquet", compression="zstd")
    stats["rows"] = len(rows)
    return stats


def blocks(stream, out):
    idx, rest = 0, b""
    while True:
        chunk = stream.read(BLOCK)
        if not chunk:
            break
        chunk = rest + chunk
        cut = chunk.rfind(b"\n")
        if cut < 0:
            rest = chunk
            continue
        rest = chunk[cut + 1:]
        yield idx, chunk[:cut + 1], out
        idx += 1
    if rest.strip():
        yield idx, rest + b"\n", out


def main():
    out = Path(sys.argv[1])
    workers = int(sys.argv[2]) if len(sys.argv) > 2 else 8
    (out / "banners").mkdir(parents=True, exist_ok=True)
    (out / "vulns").mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    total = {"lines": 0, "rows": 0, "errors": 0, "error_examples": [],
             "top_keys": Counter(), "vuln_keys": Counter(), "modules": Counter(),
             "ts_min": None, "ts_max": None, "blocks": 0}
    sem = threading.BoundedSemaphore(workers * 2)  # bound bytes in flight

    def gated():
        for item in blocks(sys.stdin.buffer, str(out)):
            sem.acquire()
            yield item

    with Pool(workers) as pool:
        for st in pool.imap_unordered(work, gated()):
            sem.release()
            total["blocks"] += 1
            for k in ("lines", "rows", "errors"):
                total[k] += st[k]
            total["error_examples"] = (total["error_examples"] + st["error_examples"])[:10]
            for k in ("top_keys", "vuln_keys", "modules"):
                total[k].update(st[k])
            for k, f in (("ts_min", min), ("ts_max", max)):
                if st[k]:
                    total[k] = f(filter(None, [total[k], st[k]]))
            if total["blocks"] % 20 == 0:
                print(f"{time.time()-t0:7.0f}s blocks={total['blocks']} rows={total['rows']}",
                      flush=True)
    total["wall_seconds"] = round(time.time() - t0, 1)
    for k in ("top_keys", "vuln_keys", "modules"):
        total[k] = dict(total[k].most_common())
    (out / "stats.json").write_text(json.dumps(total, indent=1, default=str))
    print(json.dumps({k: total[k] for k in ("lines", "rows", "errors", "wall_seconds",
                                            "ts_min", "ts_max")}, default=str))


if __name__ == "__main__":
    main()

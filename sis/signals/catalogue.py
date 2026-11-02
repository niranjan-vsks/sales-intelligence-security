"""The signal catalogue (DATA_MODEL.md 3.1). The signals table is generated from this list.

Every expression is DuckDB SQL over 1 row of the `eb` view (sis/signals/sql/02_eb.sql): a
banner of an active entity, with the held-out-free vuln columns `n_clean`, `max_clean_cvss`,
`clean_cves` and the flag `is_edge`. `{W01}`-style placeholders are the predicates of
config/what_we_sell_map.csv, filled in by `render()`.

- `fires`: does this banner fire the signal. Edge banners (DESIGN.md 5.5) never fire unless
  `edge_ok`; `render()` adds that guard.
- `sql_expr`: the entity value, an aggregate over the firing banners only.
- `evidence_value_expr`: per-banner text shown as evidence, max 300 chars (cut by evidence.py).
"""

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sis import paths

Kind = Literal["flag", "count", "max", "ratio"]

ADMIN_MODULES = ("rdp", "ssh", "telnet", "smb", "ftp", "vnc", "x11", "mysql",
                 "clickhouse-native", "weblogic")
ASSET_TAGS = ("database", "iot", "ics", "medical", "devops", "open-dir")
SMALL_CLOUDS = ("DigitalOcean", "Vultr", "Linode")
HTTP_BANNER = "http_status IS NOT NULL"


def _in(values: tuple[str, ...]) -> str:
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"


def _list(values: tuple[str, ...]) -> str:
    return "[" + ", ".join(f"'{v}'" for v in values) + "]"


@dataclass(frozen=True)
class SignalSpec:
    signal_id: str
    fact: Literal["A", "B", "C", "D", "X"]
    kind: Kind
    fires: str
    sql_expr: str
    source_field: str
    evidence_value_expr: str
    edge_ok: bool = False
    always: bool = False  # always-present: a row even when no banner fires (value 0)


SIGNALS: list[SignalSpec] = [
    SignalSpec("A_fingerprinted", "A", "flag",
               "len(cpe23) > 0 OR version IS NOT NULL", "1", "cpe23",
               "coalesce(nullif(array_to_string(cpe23, ' '), ''), "
               "concat_ws(' ', product, version))"),
    SignalSpec("A_inferred_cves", "A", "count",
               "n_clean > 0", "max(n_clean)", "vulns.cve",
               "n_clean::VARCHAR || ': ' || array_to_string(clean_cves, ' ')"),
    SignalSpec("A_max_cvss", "A", "max",
               "n_clean > 0 AND max_clean_cvss IS NOT NULL", "max(max_clean_cvss)", "vulns.cvss",
               "max_clean_cvss::VARCHAR"),
    SignalSpec("A_eol", "A", "flag",
               "list_contains(tags, 'eol-product') OR list_contains(tags, 'eol-os')", "1", "tags",
               "array_to_string(list_filter(tags, lambda t: t LIKE 'eol-%'), ' ')"),
    SignalSpec("A_os_leak", "A", "flag", "os IS NOT NULL", "1", "os", "os"),
    SignalSpec("A_cpe_per_header", "A", "ratio",
               f"{HTTP_BANNER} AND len(cpe23) > 0",
               "max(len(cpe23) / greatest(coalesce(len(http_header_names), 0), 1))", "cpe23",
               "len(cpe23)::VARCHAR || ' cpe / ' || coalesce(len(http_header_names), 0)::VARCHAR"
               " || ' headers: ' || array_to_string(cpe23, ' ')"),
    SignalSpec("B_self_signed", "B", "flag",
               "cert_self_signed OR list_contains(tags, 'self-signed')", "1", "cert_issuer_o",
               "concat_ws(' ', 'self-signed', cert_issuer_o)"),
    SignalSpec("B_expired", "B", "flag", "cert_expired", "1", "cert_expires",
               "cert_expires::DATE::VARCHAR"),
    SignalSpec("B_legacy_tls", "B", "flag",
               # an ssl_versions element is offered unless it has a leading '-'; exact match
               # on 'SSLv3' / 'TLSv1' so '-SSLv3' and 'TLSv1.2' never fire
               "ssl_version IN ('SSLv3', 'TLSv1.0') "
               "OR list_has_any(ssl_versions, ['SSLv3', 'TLSv1'])",
               "1", "ssl_versions",
               "concat_ws(' ', ssl_version, array_to_string(ssl_versions, ' '))"),
    SignalSpec("B_cert_age_days", "B", "max",
               "cert_issued IS NOT NULL AND cert_issued > TIMESTAMP '1990-01-01'",
               "max(least(greatest(date_diff('day', cert_issued, timestamp), 0), 7300))",
               "cert_issued", "cert_issued::DATE::VARCHAR"),
    SignalSpec("C_admin_services", "C", "count",
               f"module IN {_in(ADMIN_MODULES)} AND data_len > 0 "
               "AND NOT coalesce(list_contains(tags, 'cdn'), false)",
               "count(DISTINCT module)", "module", "module"),
    SignalSpec("C_windows_internals", "C", "flag",
               "list_contains(blocks, 'ntlm') OR os LIKE 'Windows%'", "1", "blocks",
               "concat_ws(' ', CASE WHEN list_contains(blocks, 'ntlm') THEN 'ntlm' END, os)"),
    SignalSpec("C_asset_tags", "C", "count",
               f"list_has_any(tags, {_list(ASSET_TAGS)})",
               f"len(list_distinct(flatten(list(list_intersect(tags, {_list(ASSET_TAGS)})))))",
               "tags", f"array_to_string(list_intersect(tags, {_list(ASSET_TAGS)}), ' ')"),
    SignalSpec("C_breadth_modules", "C", "count", "true", "count(DISTINCT module)", "module",
               "module", always=True),
    SignalSpec("C_breadth_ports", "C", "count", "true", "count(DISTINCT port)", "port",
               "port::VARCHAR", always=True),
    SignalSpec("C_components_vs_peers", "C", "max",
               f"{HTTP_BANNER} AND len(http_components) > 0", "max(len(http_components))",
               "http_components", "array_to_string(http_components, ', ')"),
    SignalSpec("C_live_web", "C", "flag", "{P01}", "1", "http_status",
               "module || ' ' || http_status::VARCHAR", edge_ok=True),
    # a gate, not a score (weight 0 in fact_c): something of theirs answered the internet.
    # 'auto' is the provider's port probe, so without a payload it shows only an open port.
    SignalSpec("C_any_service", "C", "flag", "data_len > 0 OR module NOT IN ('auto')", "1",
               "module", "module || ' ' || coalesce(data_len, 0)::VARCHAR || ' bytes'"),
    SignalSpec("D_waf", "D", "flag", "{W01}", "1", "http_waf", "http_waf", edge_ok=True),
    SignalSpec("D_edge_substitute", "D", "flag", "{W02}", "1", "http_waf", "http_waf",
               edge_ok=True),
    SignalSpec("D_security_appliance", "D", "flag", "({W03}) OR ({W04})", "1", "product",
               "coalesce(product, array_to_string(cpe23, ' '))"),
    SignalSpec("D_vpn", "D", "flag", "({W05}) OR ({W06})", "1", "module",
               "concat_ws(' ', module, CASE WHEN list_contains(tags, 'vpn') THEN 'tag:vpn' END)"),
    SignalSpec("D_hardening_headers", "D", "flag", "{W07}", "1", "http_header_names",
               "array_to_string(list_filter(http_header_names, lambda h: h IN "
               "('strict-transport-security', 'content-security-policy')), ' ')"),
    SignalSpec("X_small_cloud", "X", "flag", f"cloud_provider IN {_in(SMALL_CLOUDS)}", "1",
               "cloud_provider", "cloud_provider"),
]

BY_ID = {s.signal_id: s for s in SIGNALS}


def load_mappings(path: Path | None = None) -> dict[str, str]:
    """mapping_id -> predicate_sql from config/what_we_sell_map.csv."""
    path = path or paths.config_dir() / "what_we_sell_map.csv"
    with open(path, encoding="utf-8", newline="") as f:
        return {r["mapping_id"]: r["predicate_sql"] for r in csv.DictReader(f)}


def edge_predicate(mappings: dict[str, str]) -> str:
    """A banner describes a CDN or WAF vendor's shared edge (DESIGN.md 5.5)."""
    return f"coalesce(list_contains(tags, 'cdn'), false) OR coalesce(({mappings['W01']}), false)"


def render(spec: SignalSpec, mappings: dict[str, str]) -> str:
    """The banner-level fires predicate, never NULL, with the edge guard applied."""
    pred = spec.fires.format(**{k: v for k, v in mappings.items()})
    fires = f"coalesce(({pred}), false)"
    return fires if spec.edge_ok else f"({fires} AND NOT is_edge)"

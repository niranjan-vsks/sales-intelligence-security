-- Steps 6, 7, 9: fact scores, exposure, segment, priority, per-signal contributions
-- (DESIGN.md 5.2, 5.3). Reads `wide`: 1 row per active entity with v_<signal> (value, 0 when
-- absent) and p_<signal> (pct_in_peer, 0 when absent). Every constant is a $parameter from
-- config/scoring.yaml; {prerequisite} is the config's prerequisite list as SQL.
CREATE OR REPLACE TEMP TABLE terms AS
SELECT entity_id,
    -- fact A: 3 alternatives inside max(), then 2 additive terms
    $a_eol * v_A_eol AS t_A_eol,
    CASE WHEN v_A_inferred_cves > 0
         THEN $a_cves_base + $a_cves_cvss * v_A_max_cvss / 10 ELSE 0 END AS t_A_cves,
    $a_fingerprinted * v_A_fingerprinted AS t_A_fingerprinted,
    $a_os_leak * v_A_os_leak AS t_A_os_leak,
    $a_cpe_per_header * p_A_cpe_per_header AS t_A_cpe_per_header,
    -- fact B
    $b_self_signed * v_B_self_signed AS t_B_self_signed,
    $b_expired * v_B_expired AS t_B_expired,
    $b_legacy_tls * v_B_legacy_tls AS t_B_legacy_tls,
    $b_cert_age * p_B_cert_age_days AS t_B_cert_age_days,
    -- fact C
    $c_admin_services * least(v_C_admin_services, $cap_admin_services) / $cap_admin_services
        AS t_C_admin_services,
    $c_windows_internals * v_C_windows_internals AS t_C_windows_internals,
    $c_asset_tags * least(v_C_asset_tags, $cap_asset_tags) / $cap_asset_tags AS t_C_asset_tags,
    $c_breadth_modules * p_C_breadth_modules AS t_C_breadth_modules,
    $c_components_vs_peers * p_C_components_vs_peers AS t_C_components_vs_peers,
    -- fact D (protection present; not part of exposure)
    greatest($d_waf * v_D_waf, $d_security_appliance * v_D_security_appliance,
             $d_edge_substitute * v_D_edge_substitute, $d_vpn * v_D_vpn,
             $d_hardening_headers * v_D_hardening_headers) AS fact_d,
    {prerequisite} AS prerequisite,
    CASE WHEN v_D_waf > 0 OR v_D_security_appliance > 0 THEN 'displace'
         WHEN v_D_edge_substitute > 0 OR v_D_hardening_headers > 0 OR v_D_vpn > 0
             THEN 'partially_covered'
         WHEN {prerequisite} THEN 'untouched'
         ELSE 'low_surface' END AS segment
FROM wide;
CREATE OR REPLACE TEMP TABLE facts AS
WITH f AS (
    SELECT *,
        least(greatest(greatest(t_A_eol, t_A_cves, t_A_fingerprinted)
                       + t_A_os_leak + t_A_cpe_per_header, 0), 1) AS fact_a,
        least(greatest(t_B_self_signed + t_B_expired + t_B_legacy_tls + t_B_cert_age_days, 0), 1)
            AS fact_b,
        least(greatest(t_C_admin_services + t_C_windows_internals + t_C_asset_tags
                       + t_C_breadth_modules + t_C_components_vs_peers, 0), 1) AS fact_c
    FROM terms
), e AS (
    SELECT *, 100 * ($x_a * fact_a + $x_b * fact_b + $x_c * fact_c) AS exposure FROM f
)
SELECT *,
    exposure * CASE segment WHEN 'untouched' THEN $m_untouched
                            WHEN 'partially_covered' THEN $m_partially_covered
                            WHEN 'displace' THEN $m_displace
                            ELSE $m_low_surface END AS priority
FROM e;
-- Step 9: contribution = the signal's term x its fact's exposure weight x 100, before the clip.
-- Inside fact A's max() only the winning alternative contributes (ties: eol, cves,
-- fingerprinted); the CVE alternative is credited to A_inferred_cves.
CREATE OR REPLACE TEMP TABLE contrib AS
SELECT entity_id, signal_id, contribution FROM (
    SELECT entity_id,
        100 * $x_a * CASE WHEN t_A_eol > 0 AND t_A_eol >= t_A_cves
                               AND t_A_eol >= t_A_fingerprinted THEN t_A_eol ELSE 0 END
            AS A_eol,
        100 * $x_a * CASE WHEN t_A_cves > 0 AND t_A_cves > t_A_eol
                               AND t_A_cves >= t_A_fingerprinted THEN t_A_cves ELSE 0 END
            AS A_inferred_cves,
        100 * $x_a * CASE WHEN t_A_fingerprinted > 0 AND t_A_fingerprinted > t_A_eol
                               AND t_A_fingerprinted > t_A_cves THEN t_A_fingerprinted ELSE 0 END
            AS A_fingerprinted,
        100 * $x_a * t_A_os_leak AS A_os_leak,
        100 * $x_a * t_A_cpe_per_header AS A_cpe_per_header,
        100 * $x_b * t_B_self_signed AS B_self_signed,
        100 * $x_b * t_B_expired AS B_expired,
        100 * $x_b * t_B_legacy_tls AS B_legacy_tls,
        100 * $x_b * t_B_cert_age_days AS B_cert_age_days,
        100 * $x_c * t_C_admin_services AS C_admin_services,
        100 * $x_c * t_C_windows_internals AS C_windows_internals,
        100 * $x_c * t_C_asset_tags AS C_asset_tags,
        100 * $x_c * t_C_breadth_modules AS C_breadth_modules,
        100 * $x_c * t_C_components_vs_peers AS C_components_vs_peers
    FROM facts
) UNPIVOT (contribution FOR signal_id IN (
    A_eol, A_inferred_cves, A_fingerprinted, A_os_leak, A_cpe_per_header,
    B_self_signed, B_expired, B_legacy_tls, B_cert_age_days,
    C_admin_services, C_windows_internals, C_asset_tags, C_breadth_modules,
    C_components_vs_peers))
WHERE contribution > 0

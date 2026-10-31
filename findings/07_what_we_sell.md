# 07_what_we_sell.md

WORKING DEFINITION. ASSIGNMENT.md names only the category ("cybersecurity
software"), so this list is every value found in the file that names a
security product, vendor or control, grouped by what it is. Each value is
quoted from a values/ file; the column is given per group. Stage 2
configuration form: 07_what_we_sell_map.csv (SQL predicate per group).
Counts FULL, from queries/07b_negative.py -> 07_negative.json.

## 1. Web application firewall / DDoS protection (column `http_waf`, values/http_waf.csv)

Provider-detected, 76 values. Security products (mapping W01, 1,089,388 rows):
Incapsula (Imperva Inc.) 519,798; Cloudflare (Cloudflare Inc.) 349,918;
Kona SiteDefender (Akamai) 159,032; FortiWeb (Fortinet) 31,161; SonicWall
(Dell) 8,099; NetScaler AppFirewall (Citrix Systems) 4,614; 360WangZhanBao
(360 Technologies) 3,586; Shadow Daemon (Zecure) 2,155; BIG-IP AppSec Manager
(F5 Networks) 2,146; DDoS-GUARD 1,806; DataPower (IBM) 1,305; ZScaler
(Accenture) 1,054; Sucuri CloudProxy 923; ModSecurity (SpiderLabs) 285;
Safeline 236; BitNinja 141; Imunify360 106; Barracuda 83; SecureSphere
(Imperva) 47; Wordfence 22; UTM Web Protection (Sophos) 16; WatchGuard 8;
Alert Logic 4; and 37 more under 1,000 rows each (full list in the map).

CDN / load-balancer labels the same detector emits (mapping W02, substitute,
476,810 rows): Cloudfront (Amazon) 310,736; AWS Elastic Load Balancer 132,281;
CacheWall (Varnish) 15,289; LiteSpeed 3,857; Azure Front Door 3,992; Fastly
3,766; Squarespace 3,222; BIG-IP Local Traffic Manager 1,727; and 7 more.

## 2. Network security appliances: firewall, VPN, secure access (column `product`, values/product.csv)

Mapping W03, 28,342 rows: SonicWall 11,720; Citrix Netscaler 4,627;
Fortinet FortiGate 1,935 (plus FortiGate-60F 295, -40F 286, -100F 183 and
other model strings); Checkpoint VPN-1 / Firewall-1 1,571; Zscaler Cloud
Services 1,510; Ivanti Endpoint Manager Mobile (EPMM) 1,238; Sophos SSL VPN
User Portal 1,179; Connectra Check Point Web Security httpd 481; Check Point
Firewall 290; Sophos User Portal 243; Cisco ASA SSL VPN 224; OpenVPN Access
Server CWS 194; Stormshield Network Security 137; Barracuda 300 spam filter
135; Pulse Secure 28; ZyXEL ZyWALL sshd 22; WireGuard UI 18.

## 3. Security vendor in the CPE fingerprint (column `cpe23`, values/cpe23_elements.csv)

Mapping W04, 586,078 rows: cpe:2.3:a:imperva:incapsula 519,798;
cpe:2.3:a:fortinet:fortiweb 31,161; cpe:2.3:a:f5:big-ip 11,949;
cpe:2.3:o:sonicwall:sonicos 8,099;
cpe:2.3:a:citrix:netscaler_application_delivery_controller 4,614;
cpe:2.3:o:fortinet:fortios 2,337; cpe:2.3:a:f5:big-ip_application_security_manager
2,146; cpe:2.3:a:zscaler:client_connector:6.2 1,510; cpe:2.3:h:fortinet:fortigate 1,439.
(cpe:2.3:a:f5:nginx, 617,139, is the web server, not a security product,
and is excluded.)

## 4. VPN / IPsec endpoints (columns `module`, `tags`)

module (W05, 232,028 rows): ike 142,791; ike-nat-t 44,810; l2tp 19,058;
openvpn 10,806; pptp 10,575; checkpoint-hostname 3,988.
tags (W06): vpn 127,896.

## 5. Security controls a company runs itself (column `http_header_names`)

strict-transport-security, content-security-policy (W07, substitute,
401,994 rows). Also present, not mapped: x-frame-options,
x-content-type-options, x-xss-protection, referrer-policy,
permissions-policy (values/http_header_names_elements.csv).

## 6. Provider security labels (column `tags`, values/tags_elements.csv)

honeypot 250,439; eol-product 244,327; self-signed 132,202; eol-os 6,036;
ssh-bad-key 80; compromised 77; c2 31; malware 5; doublepulsar 1.

## 7. Security certifications / roles

None. No column holds certifications, compliance frameworks, or job roles.
The file describes hosts, not organisations.

## 8. Not a security product though the name suggests it

- `module` values darktrack-rat, remcos-pro-rat, orcus-rat, ta14-353a: probe
  names. On Google IPs 16 of 31,763 such rows have a payload; on Aliyun
  IPs every row does, and Aliyun holds most honeypot-tagged rows
  (07_ground_truth.md).
- http_component_category "Security": values/http_component_category_pairs.csv
  is a co-occurrence table (component x categories of the same row), not
  the provider's component -> category map; the flattener did not keep the
  per-component mapping. Do not read it as "jQuery is a security product".

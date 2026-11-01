# sales-intelligence-security

Sales intelligence platform over a Shodan banner export. Design: DESIGN.md, tables: DATA_MODEL.md, build order: cards/.

## How this repo is built

Process: one card per phase in cards/P<N>.md, built under the rules in cards/README.md.
Doctrine: `/phase`. The gates in PHASE_CONFIG.md are binding, not advisory.
Config: PHASE_CONFIG.md holds every path and command. Read it before assuming one.
Release: `/forge release` runs the security gate (strix) at P5.
Never touch findings/. Never commit anything under $SIS_DATA. Do not push.

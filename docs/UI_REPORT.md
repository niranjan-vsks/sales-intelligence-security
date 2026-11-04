# UI report (cards/P5_1.md)

Walked on 2026-11-04 with Playwright (Chromium) against `sis serve` on bundle
`20261102-0000-p6-1.1.0` (487,133 accounts, 84,313 simulated events), then against the live URL
after the redeploy. Untouched example: wide.ad.jp (rank 1). Displace example: kuroit.com (the
displace account with the worst recent change).

## Screenshots

| file | what it shows |
|---|---|
| [01-overview-1280-dark.png](ui/01-overview-1280-dark.png) | Overview, dark: 4 tiles, segment split, exposure histogram with the hover readout on the 20 to 30 bucket, top countries, most common reasons, Start here. |
| [02-overview-1280-light.png](ui/02-overview-1280-light.png) | The same page in the light theme, with the hover glow on the Untouched tile. |
| [03-accounts-filtered-1280-dark.png](ui/03-accounts-filtered-1280-dark.png) | Accounts with 2 filters applied (segments Untouched + Has a vendor, country DE): 51,256 accounts, filter bar on 1 row, change dots on changed accounts. |
| [04-accounts-filtered-1280-light.png](ui/04-accounts-filtered-1280-light.png) | The same filtered list in the light theme. |
| [05-detail-untouched-1280-dark.png](ui/05-detail-untouched-1280-dark.png) | Untouched account detail: exposure, rank, Why panel with the first evidence block expanded, Changes, the 4 facts, Protection (none observed). |
| [06-detail-displace-1280-light.png](ui/06-detail-displace-1280-light.png) | Displace account detail, light: protection by vendor in words, 3 simulated changes, Technical details expanded (signal ids, values, peer percentiles). |
| [07-detail-marked-prospect-1280-dark.png](ui/07-detail-marked-prospect-1280-dark.png) | After clicking "Mark as prospect": the confirmation swapped in place of the 2 buttons. |
| [08-about-1280-dark.png](ui/08-about-1280-dark.png) | About: DESIGN.md sections 1, 5, 6 and 7 at a 760 px reading width. |
| [09-overview-390-dark.png](ui/09-overview-390-dark.png) | Overview at 390 px: tiles 2 by 2, panels stacked, no horizontal scroll. |
| [10-accounts-filtered-390-dark.png](ui/10-accounts-filtered-390-dark.png) | Accounts at 390 px with the same 2 filters: table rows become stacked cards. |
| [11-detail-untouched-390-light.png](ui/11-detail-untouched-390-light.png) | Untouched detail at 390 px, light, evidence expanded; snippets wrap. |
| [12-about-390-light.png](ui/12-about-390-light.png) | About at 390 px, light. |

## Checks

- **Accessibility (Lighthouse 13.6.0, accessibility category, default dark theme):** overview 100,
  accounts 100, detail (untouched) 100, detail (displace) 100, about 100.
- **axe-core 4.10.2, WCAG 2 A and AA, every `<details>` opened:** 0 violations on overview,
  filtered accounts, both detail pages and about, in both dark and light. That includes colour
  contrast in the light theme, which Lighthouse did not see.
- **Console:** 0 errors and 0 warnings across the walk (5 distinct pages, 12 screenshots), local
  and live; 0 failed requests live.
- **Width:** `scrollWidth - clientWidth` = 0 on every page at 1280 and 390 px.
- **Palette:** segment colours (untouched = accent blue, partially covered = amber, displace =
  violet, low surface = grey) pass the dataviz validator's CVD and normal-vision separation in
  both themes (the grey's low chroma is intended). Fact colours A to D pass in dark and sit in the
  CVD warn band in light, which is allowed because every fact bar is labelled with its name.
- **Theme:** dark by default. The header toggle switches to light; the choice is kept in
  localStorage and applied before first paint, so a page load never flashes the other theme.

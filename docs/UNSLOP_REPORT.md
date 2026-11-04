# Copy pass (P5.3)

Every change made to reader-facing text, as before and after. Scope: sis/api/labels.py,
sis/api/templates/, docs/ABOUT.md, README.md and the prose paragraphs of DESIGN.md. No number,
signal meaning or claim was changed. Terms follow docs/ABOUT.md.

## sis/api/labels.py

| before | after | why |
|---|---|---|
| Segment name "Has a vendor (displace)" | "Has a vendor" | ABOUT.md's segment name. Shows in badges, the rank line ("#13 in Has a vendor") and the segment-change event. |
| Partially covered, 1 line: "A CDN edge in front, the rest open" | "An edge platform, VPN or hardening headers, no security product" | The old line named 1 of the 3 things that put an account in this segment. Now matches ABOUT.md's meaning. |
| Low visible surface, 1 line: "Too little visible to judge" | "Nothing of theirs answered the scan" | Since P3.1 the segment means nothing answered (ABOUT.md, DESIGN.md 12). The old line described the pre-P3.1 meaning. |

## sis/api/templates/overview.html

| before | after | why |
|---|---|---|
| Has a vendor tile: "15.9% of accounts, to displace" | "15.9% of accounts" | The tile is already named Has a vendor; the tail added nothing. |

## sis/api/templates/account.html

| before | after | why |
|---|---|---|
| "Simulated second delivery: these changes were manufactured to test change detection and did not happen." | "...these changes were planted to test change detection and did not happen." | ABOUT.md's word for the same thing ("known changes planted"). |

No other template string changed. The rest were already plain: labels, empty states, panel
subtitles, the theme toggle's accessible names.

## README.md

| before | after | why |
|---|---|---|
| "the 4 bars show which of the 4 facts drive it (old software, neglected certificates, ...)" | "(visibly old software, neglected certificates, ...)" | The fact's name in ABOUT.md and in the app. |
| Heading "Honest status" | "Status" | A section that calls itself honest invites the opposite reading; the content is unchanged. |

## DESIGN.md (prose only)

| section | before | after |
|---|---|---|
| 4 | "Specified in cards/P2.md. The rule is simple and the write-up says why it is right for this data:" | "Specified in cards/P2.md. The rule, and why it fits this data:" |
| 4 | "The write-up states explicitly that the `*-rat` probe modules are not detections (16 of 31,763 ...) and are ignored." | "The `*-rat` probe modules are not detections (16 of 31,763 ...) and are ignored." |
| 4 | "What is lost and said so: entities that ..." | "What is lost: entities that ..." |
| 6 | "In plain words: the top of the list is about 28 times richer ..." | "The top of the list is about 28 times richer ..." |
| 6 | "The honest limits, stated in the write-up: label_kev is downstream ..." | "Limits: label_kev is downstream ..." |
| 7 | "... with their validation protocols and cost accounting. They are described here so the reader can judge the design, with the status stated plainly." | "... with their validation protocols and cost accounting." |
| 10 | "This is how it was built, honestly." | "This is how it was built." |
| 10 | "Those 2 buttons are the first true labels this system will ever have." | "... the first true labels this system has." |
| 12 | "The segment is named for what we can see, and the write-up says so." | "The segment is named for what we can see." |

Sections 1, 5, 6 and 7 are what the live About page renders, so 3 of these edits (the 2 in
section 6 and the 1 in section 7) are visible in the app.

## docs/ABOUT.md

No changes. The copy is already plain.

## Left alone, for the architect

These look wrong or unclear, but fixing them would change a claim or touch something out of
scope:

1. **The About page does not render docs/ABOUT.md.** `/about` still renders DESIGN.md sections
   1, 5, 6 and 7 (sis/api/routes.py `ABOUT_SECTIONS`). Wiring ABOUT.md in is a route change.
2. **ABOUT.md, "Reading an account page": "The header gives the score, the rank, and the peer
   group."** The account header has no peer group: `peer_group` is NULL for every account in
   the bundle (P5.1 deviation 1). Either drop "and the peer group" or store the peer group.
3. **ABOUT.md: "The 4 bars show which facts drive the score."** Protection present is 1 of the 4
   bars and does not drive the score (ABOUT.md says so itself a few lines up).
4. **ABOUT.md, "For engineers": "the repository README linked in the footer".** The footer has
   no README link.
5. **DESIGN.md 11: "UI polish: server-rendered tables and 1 detail page ... Not more."** Since
   P5.1 there is also an overview page; the next sentence says so, so the bullet contradicts
   itself.
6. **DESIGN.md 6, table: "the honest exam"** (label_any_tested). Same issue as README's "Honest
   status", but it is in a table, which was out of scope.
7. **The feedback confirmation "Marked as prospect. Thank you."** comes from sis/api/routes.py,
   not a template, so it was not in scope. It is fine as it is.

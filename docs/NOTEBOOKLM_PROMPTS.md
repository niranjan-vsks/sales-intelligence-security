# NotebookLM setup and prompts

## What to upload as sources, in this order

1. docs/PRIMER.md. The plain-language explanation. Upload first.
2. ASSIGNMENT.md. The original task.
3. findings/REPORT.md. The explorer's 133-line summary of what the data
   contained. It is technical; the primer decodes it.
4. findings/08_candidates.md. The signal list with evidence. Technical.
5. EXPLORATION.md. The plan the explorer followed. Shows the method.
6. The job description, so the generations connect the project to what
   Firmable says it is hiring for.
7. Your resume, for context only. The prompts below tell NotebookLM to
   use it for at most 1 short connection per overview, never as a topic.

Do not upload the values folder, the CSVs, or the queries. They are tables
and code and will only add noise.

When the design documents exist (DESIGN.md, DATA_MODEL.md, the cards), add
them and regenerate. The primer will be updated at the same time.

## Master prompt: audio overview

Paste this into the customise box of the audio overview.

```
You are explaining a 5-day take-home project to a smart listener who is
preparing to present it in a job interview. The listener understands
software basics but none of the security or networking jargon. Use
docs/PRIMER.md as the primary source for language and structure, and
treat REPORT.md and 08_candidates.md as the evidence behind it.

Follow this order:
1. The business problem in 1 minute: a cybersecurity company's sales team
   needs a ranked list of businesses that need security help.
2. What the data turned out to be, and why it was a trap: internet scan
   banners, not company records; half the file is 2 network operators;
   only 7 percent of lines belong to a named business; the whole file is
   1 day of scanning so nothing is "new" inside it.
3. How businesses were reconstructed from banners (entity resolution,
   the 50-address rule, the disqualifiers).
4. The 4 families of signals in plain words, and the negative signal:
   businesses with a live service and no protection are the first call,
   businesses behind a WAF are a displacement play.
5. The traps that were caught: inferred CVEs, probe names that look like
   malware detections, honeypots, operator domains.
6. How success is measured without sales data: held-out proxy labels,
   precision at the top of the ranking.
7. Why no LLM is used for scoring, and what scaling to 1,000 files a month
   changes.
8. How the work was organised: an architect session, an explorer session,
   builder sessions, with every number traceable to a saved query.

Define every technical term the first time it comes up, in 1 sentence,
the way the primer does. Repeat the key numbers from section 10 of the
primer. Do not invent numbers or signals that are not in the sources.
Spend the most time on sections 2, 3 and 4. End with the 9 interview
questions and short answers from the primer.

The job description and the resume are context, not topics. Use them in
exactly 2 places: once near the start, in 1 or 2 sentences, to say what
kind of role this project is a test for (hands-on backend lead, Python
and FastAPI services, AI agents with evals and cost tracking); and once at
the end, in at most 3 sentences, to connect the project's design choices
to those expectations. Do not summarise the resume, do not list past
employers or projects, do not compare the candidate to the requirements.
At least 90 percent of the running time is about the project and the
data.
```

## Master prompt: video overview

Paste this into the customise box of the video overview.

```
Make an explainer for someone who must present this project in an
interview. Audience knows basic software, not security. Source of truth
for wording: docs/PRIMER.md. Source of truth for numbers: REPORT.md.

Structure the video as 6 chapters with a title card each:

Chapter 1, "The ask": sales team, cybersecurity software, rank businesses
that need help. 1 slide.

Chapter 2, "What was in the file": show a single banner as a card with
its parts labelled (address, port, software, certificate, weaknesses,
tags). Then show the file as 14.6 million such cards. Then show the
split: 62 percent belongs to 5 network operators, 7 percent to named
businesses, the rest anonymous. Explain CDN and WAF as a curtain in front
of the real servers.

Chapter 3, "Finding the companies": animate banners grouping under a
domain name. State the 50-address rule. Show the disqualifiers removing
operators, honeypots and anonymous rows. End on 485,089 businesses.

Chapter 4, "The signals": 4 panels, 1 per family: old software,
neglected certificates, exposed surface, already protected. For each,
1 concrete example in plain words. Then the 2 output lists: untouched
prospects (131,104) and displacement prospects.

Chapter 5, "The traps": 4 short cards, 1 per trap, each with the wrong
conclusion a naive build would reach and the check that caught it.

Chapter 6, "Proving it and scaling it": the 5-station factory diagram
(ingest, resolve, signals, score, evaluate) feeding a small website.
Held-out proxies and precision at k. Monthly files and diffing as the
real "right now". No LLM in scoring, and why.

Use the exact numbers from the primer's section 10 table and no others.
Define jargon on screen the first time it appears. Keep each chapter
under 2 minutes.

The job description and resume are background only. Use them in 1 closing
card, at most 3 bullet points, mapping the project's choices (offline
batch scoring, deterministic rules instead of LLM calls, evaluation
against held-out labels, cost and scale stated) to what the role asks
for. No resume content anywhere else in the video. No slide about the
candidate.
```

## Suggested flashcard and quiz focus

Ask NotebookLM to build flashcards from: the glossary in PRIMER.md, the
section 10 numbers, and the 9 interview questions. Ask the quiz to focus
on "why" questions: why org is not the company, why CVEs are inferred,
why proxies are held out, why scoring is offline, why no LLM.

## Mind map focus

Root: the platform. Branches: the data, entity resolution, the 4 signal
families plus disqualifiers, the 5 stations, evaluation, scale, dev loop.

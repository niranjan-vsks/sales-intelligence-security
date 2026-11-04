# Demo guide

Live app: https://sis-niranjan.fly.dev/ . No login. Dark theme by
default; the toggle is in the header.

## 5-minute walk

1. **Overview** (the landing page). Read the 4 tiles: active accounts,
   untouched, has a vendor, changed since last delivery. The segment bar
   and the exposure histogram show the shape of the book. "Start here"
   lists the 10 untouched accounts with the highest priority.
2. **Accounts.** Click the Untouched tile or the Accounts link. Try:
   - segment chips: Untouched is the first-call list, Has a vendor is the
     displacement list
   - country: pick 1 to see the peer-relative scoring in a smaller pool
   - sort: priority (default), exposure, recent change
   - search: any part of a domain name
3. **An account.** Open the first row. Top to bottom:
   - header: exposure out of 100, rank overall and within segment, peer
     group, hosting operator, feedback buttons
   - 4 fact bars: old software, neglected certificates, exposed surface,
     protection present
   - Why: the top reasons in plain words, each with its share of the
     score; expand 1 to see the raw banners (address, port, service,
     time, first lines of the response)
   - Protection present: the vendor or edge platform, when any
   - Changes: events between the 2 deliveries, marked as simulated
   - Technical details: signal ids, raw values, percentiles, versions
4. **Feedback.** Click Mark as prospect. The confirmation swaps in; the
   mark is appended to a file on the server and is the first real label
   the ranking will be measured against.
5. **About.** What the tool is, what the score means, what it does not
   do. The footer links to the repository and the design document.

## 3 accounts worth showing

Use the list, Untouched, sort by priority, and open the first 3. They
illustrate the 3 positive facts: a version with inferred
vulnerabilities, an expired or self-signed certificate, and remote-admin
services open to the internet. Then switch the segment to Has a vendor
and open the first row to show the incumbent named in the evidence.

## Run locally

```
uv sync
uv run sis serve        # http://localhost:8000, uses the latest bundle under $SIS_DATA/serve
```

The bundle is built by `uv run sis export` from the pipeline outputs;
README.md has the full pipeline commands.

## What to say about the numbers

- 14.6 million banners in, 487,133 businesses out.
- 300,849 untouched, 77,530 with a vendor already.
- Top 1,000 by priority: 28 times the base rate of tested vulnerabilities.
- 1 Fly.io machine, 7.73 USD a month.
- Ingest 12 minutes a file; 1,000 files a month fit on 1 worker, storage
  is the first real limit.

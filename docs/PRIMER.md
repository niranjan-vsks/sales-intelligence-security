# The Sales Intelligence Platform, explained from zero

This document explains the whole project in plain language. It assumes you
know what a website, a server and a database are, and nothing else. Read it
top to bottom once. Every technical word is defined the first time it is
used, and again in the glossary at the end.

---

## 1. The story in 1 paragraph

A company that sells cybersecurity software has a sales team. The sales team
has a problem: there are millions of businesses out there, and only some of
them need security help badly enough to buy. Calling all of them is a waste.
So the company wants a tool that looks at raw data about businesses and
says: these are the ones to call first, and here is why. We were given 1
enormous file of raw data and 5 days. We have to turn that file into a
ranked list of companies, put the list on a website the sales team can open,
and explain how we would keep the list fresh as new files arrive every month.

## 2. The cast

- **Firmable**: the company giving us the assignment. They build AI-driven
  business data products. They are hiring, and this is their test.
- **The cybersecurity software company**: imaginary. We are building for
  their sales team. We do not know what exact product they sell, only that it
  is "cybersecurity software". We keep that general.
- **The salesperson**: the user of our tool. They want a list of companies,
  sorted by how badly each one needs security help, with a reason they can
  mention on a call.
- **The prospect**: a business that might buy. In our data, a prospect shows
  up as a website or a server on the internet, never as a neat company
  record.

## 3. What the file actually is

### 3.1 Internet scanning

Every computer that is reachable on the internet has an address, called an
IP address, which looks like 141.193.213.20. On each address, programs
listen on numbered doors called ports. Port 443 is usually a secure website.
Port 22 is usually a remote login tool called SSH. Port 3389 is usually
Windows remote desktop.

Some organisations run scanners: programs that knock on every door of every
address on the internet and write down what answers. The most famous one is
called Shodan. Shodan is like a search engine for devices instead of web
pages. When a scanner knocks on a door and something answers, the answer is
called a banner. A banner is whatever the program behind the door said when
asked: a web page, a version number, a login prompt, a certificate.

### 3.2 Our file is 14.6 million banners

The file we were given is a Shodan export. It is 1 file, compressed to 16.4
GB, and uncompressed it is 123 GB. It has 14.6 million lines. Each line is
1 banner: 1 address, 1 port, 1 moment in time, and everything the scanner
saw. The whole file was collected in about 1 day, on 2026-10-25 and
2026-10-26, and 96 percent of it in a single hour.

Each banner can contain:

- where the address is (country, city)
- who owns the block of addresses (an internet provider, a cloud company,
  a content delivery network)
- the website's name, if the address has one
- the raw response text
- the software and version that answered, if the scanner could tell
- a list of known security weaknesses that software version is known for
- details of the security certificate, if the door uses encryption
- tags the scanner added, like "cloud", "honeypot", "self-signed"

### 3.3 The 3 big surprises

**Surprise 1: companies are not in the file.** There is no row that says
"Acme Ltd, 200 employees, retail". There are only addresses and ports. To
find a company we have to work out which banners belong together. That is
the hardest part of the project and it is called entity resolution or
roll-up.

**Surprise 2: most of the file is not companies at all.** Half the file
belongs to 2 big network operators. The biggest is Incapsula, a company
that sits in front of other people's websites to protect them. The second
is Google's cloud. When a scanner knocks on Incapsula's doors, Incapsula
answers for thousands of customers at once, so you see Incapsula, not the
customer. 93 percent of the lines cannot be tied to any customer business.
The usable part is about 1.07 million lines, which group into 485,089
named businesses, identified by their website domain.

**Surprise 3: there is no "right now" inside the file.** Everything was
scanned in 1 day. Nothing in the file is older or newer than anything else.
So we cannot say "this company got worse this month" from 1 file. Freshness
has to come from comparing this month's file to last month's. The
assignment says hundreds of files arrive every month, so that comparison is
part of our design, even though we only have 1 file to test it on.

## 4. The words you will hear, explained

**IP address.** The numeric address of a machine on the internet.

**Port.** A numbered door on that machine. Different services use different
doors.

**Service.** The program behind a door. A website, a database, a remote
login.

**Banner.** What the service said when the scanner knocked. 1 line of our
file.

**Domain and hostname.** A domain is a website name a business owns, like
jamasoftware.com. A hostname is a more specific name of 1 machine, like
mail.jamasoftware.com. The file records these when the scanner can look them
up. Reverse DNS is the lookup from address back to name. When no name is
found, the banner is anonymous and we cannot attach it to a business.

**Network operator, org, ASN.** Every block of addresses is registered to
someone: a telecom, a cloud provider, a hosting company. The file calls that
owner "org" and gives it a number called ASN. Important: this is the
landlord, not the tenant. A small shop hosted on Amazon shows "Amazon" as
org. So org is useless for finding the customer, and we had to prove that.

**CDN.** Content delivery network. A set of servers around the world that
sit in front of a website to make it fast and to absorb attacks. Cloudflare,
Akamai and Incapsula are CDNs. For us, a CDN is a curtain: behind it you
cannot see the customer's real servers.

**WAF.** Web application firewall. A filter in front of a website that
blocks malicious requests. Incapsula, Cloudflare and Sucuri sell WAFs. If a
business already has a WAF, it has already bought web security from someone.
That is a negative signal for selling a competing product, or a positive one
for displacing the incumbent.

**Cloud provider.** Amazon, Google, Microsoft, and smaller ones like
DigitalOcean, Linode, Vultr. A business renting servers there.

**TLS certificate.** The digital ID a secure website shows to prove it is
who it says. Certificates have an issue date and an expiry date. A
self-signed certificate is one the owner made up themselves instead of
getting it from a trusted authority; browsers warn about it. An expired
certificate means nobody renewed it. Both suggest nobody is looking after
that service.

**Fingerprint, CPE, version.** When a service answers, it often says what
software it is, like "Apache 2.2.15". The scanner records this in a standard
format called CPE. Knowing the exact version is what lets anyone, including
attackers, look up what is wrong with it.

**CVE.** A published, numbered description of a known security weakness in a
specific piece of software, like CVE-2021-44228. There are hundreds of
thousands of them. The file attaches CVEs to banners based on the version
seen. Important trap: 99 percent of those are inferred from the version
string, not tested. The scanner saw "Apache 2.2.15" and listed every CVE
ever published for that version. It did not check whether the server was
actually exploitable.

**CVSS, EPSS, KEV.** 3 ways of saying how bad a CVE is. CVSS is a severity
score from 0 to 10. EPSS is a probability that it will be exploited soon.
KEV is a short list kept by the US government of weaknesses that are
actually being exploited in the wild. KEV is the most trustworthy of the 3
for "this matters now".

**End of life, EOL.** Software the maker no longer updates. Anything found
after that point stays unfixed forever.

**Honeypot.** A fake server set up on purpose to attract attackers and study
them. It looks vulnerable but it is bait, not a business. We remove them.

**RAT, C2.** Remote access trojan and command-and-control: malware and the
servers that control it. The scanner has probes named after specific
malware. Trap: the probe name tells you what was tried, not what was found.
We proved those rows are almost all empty.

**SSH, RDP, SMB, Telnet, FTP, NTLM.** Old or sensitive ways to log in to or
share files with a machine. Seeing them open on the public internet is a
classic sign of a business that is not managing its exposure.

**Security headers, HSTS, CSP.** Small settings a website sends to browsers
to harden itself. Their presence hints at a security-aware web team.

**JSONL, zstd, Parquet, DuckDB.** The file formats and tools. JSONL is 1
JSON object per line. zstd is the compression. Parquet is a column-oriented
file format that is fast to query. DuckDB is a small database engine that
runs on a laptop and queries Parquet files far larger than memory. We
converted the 123 GB file into 2.5 GB of Parquet once, then ran every
question against that.

**Entity, roll-up, entity resolution.** Taking many banners and deciding
they belong to 1 business. Our rule: a business is a domain name that
covers 50 addresses or fewer. Domains covering more than 50 addresses are
operators, not customers. The number 50 is a dial we can turn.

**Signal.** A fact about a business that changes how likely it is to need
or buy security help. Positive signals raise the score. Negative signals
lower it or move the business to a different list.

**Lift.** How much more common something is in a group than overall. If 16
percent of all businesses have a known-vulnerable version, and 80 percent
of businesses with a self-signed certificate do, the lift is 5. We used
lift to decide which signals carry information.

**Peer group.** Businesses that should be compared with each other. We
compare a service with other services of the same type in the same
country, so that an old certificate on a small appliance is judged against
other small appliances.

**Ground truth and proxy.** Ground truth would be a record of who actually
bought. We do not have it. A proxy is a stand-in: for example, whether a
business has a weakness on the KEV list. We check whether our ranking puts
those businesses near the top. We are honest that a proxy is not the same
as a sale.

**Precision at k.** Of the top k businesses our ranking produces, what
fraction are "good" by the proxy. The main number we will report.

**Offline versus live.** Offline means computed in advance, in a batch.
Live means computed when the user clicks. We score everything offline and
the website only reads the finished answer. That keeps the site cheap and
fast.

## 5. What we found: the signals, in plain words

The exploration produced 17 candidate signals and 3 disqualifiers. They
group into 4 underlying facts about a business, plus the disqualifiers.

**Fact A: visibly old software.** The business runs servers that announce
their software version, and that version has published weaknesses or is
no longer supported. This is the strongest family. Caveat: the weaknesses
are inferred from the version, not tested.

**Fact B: neglected certificates.** Self-signed, expired, or much older than
peers. Means nobody is maintaining that service.

**Fact C: exposed surface.** Remote login, file sharing, databases, Windows
internals reachable from the internet. Also simply having many different
services open, more than peers. Windows login banners even leak the
business's internal network name.

**Fact D: already protected.** A WAF or CDN in front, a known firewall
vendor on the edge, hardening headers present. This is the negative side.
A business with a WAF has already bought from someone.

**Disqualifiers.** Rows that belong to operators, not customers. Honeypots
and scanners. Anonymous addresses with no name.

**The target list.** 131,104 businesses, 27 percent of all named ones, have
a live website or an exposed admin service and no sign of any security
product. That is the list a salesperson wants first.

## 6. What we are building

Think of it as a factory with 5 stations, then a shop window.

**Station 1: ingest.** Take a raw compressed file, read it line by line
without loading it all, and write it out as Parquet. Record which file it
came from, so the same file delivered twice is detected and skipped.

**Station 2: resolve entities.** Decide which banners belong to which
business. Apply the disqualifiers. Output: 1 row per business, with the
list of its banners.

**Station 3: compute signals.** For each business, compute every signal
from section 5. Store the evidence: which banner, which line, which value.

**Station 4: score.** Combine the signals into a number per business, using
peer-relative comparison. Separate the output into lists: untouched
prospects, displacement prospects, and not-a-prospect.

**Station 5: evaluate.** Hold the proxy labels out of scoring, then check
whether the top of the ranking is richer in them than random. Report the
number.

**The shop window.** A small website that reads the finished table of
485,089 businesses. A salesperson can search, filter, sort, open a business,
and read the evidence. It never touches the 123 GB file. It is hosted on a
free or near-free plan and shared by link.

**The monthly loop.** When a new file arrives, stations 1 to 5 run again,
and the new table is compared with the previous one. Differences are the
real "right now": a certificate just expired, a WAF disappeared, a new door
opened. We only have 1 real file, so we prove this on a second file we
manufacture by changing the real one in known ways, and we say so.

**The 2 places an LLM is used, and the 1 place it is not.** Scoring uses
no LLM at all; it is rules on structured fields. An LLM is used, first, to
read a business's website title and page text and say what kind of
business it is, since the scan cannot tell a dental clinic from a data
centre. Second, when a salesperson marks an account as a prospect, an LLM
writes 2 plain sentences per finding for a report card, using only our own
evidence, and an automatic check rejects anything it says that the
evidence does not contain. Both uses are tested against hand-labelled
samples and every call is logged with its cost.

**The agent door.** The same search and lookup functions are also exposed
as tools for an AI agent (an MCP server), so a salesperson can ask in
plain language and get grounded answers. It is the last, optional piece.

## 7. The dynamics: why these choices

**Why score offline.** 123 GB cannot live in a web database on a budget.
Scoring is batch work anyway. The website only needs the small result.

**Why no LLM in scoring.** Every signal is a deterministic rule on
structured fields. An LLM would add cost, add errors, and make the ranking
impossible to explain. The assignment asks to prove any LLM is right and to
state its cost; the cleanest answer is to not need one. The only optional
use is writing a short evidence summary per business for the salesperson,
and if we do that we state the cost per business and check a sample by hand.

**Why entity resolution is the heart.** Without it we would be ranking
Incapsula's servers. Everyone who skips this step ships a list of CDNs.

**Why we hold proxies out.** If we use "has a KEV weakness" as a signal and
also as the test, the test is rigged. So some labels are features and
others are held back as the exam.

**Why the traps matter.** Inferred CVEs, probe names that look like malware
detections, honeypots, operator domains. Each would make a naive ranking
confidently wrong. Catching them is evidence we understood the data, which
is what the assignment explicitly asks for.

**Why minimal UI and no email drafting.** The assignment says those are not
the interesting part. We say in the write-up that we cut them on purpose.

**What breaks at scale.** 1,000 files a month at 16 GB each is 16 TB a
month. A laptop pipeline does not survive that. The design says what
changes: parallel workers per file, object storage for Parquet, a job queue,
and a merge step that only recomputes businesses whose banners changed.

## 8. How we are building it: the dev loop

The work is split across 3 roles, all run as separate AI sessions with a
human directing them:

1. **The architect** (this session). Reads the assignment, writes the
   exploration plan, reads the findings, writes the design and build cards.
   Writes no code.
2. **The explorer** (an Opus session). Executed the exploration plan against
   the full file, wrote every number into a findings folder with the query
   that produced it, and reported deviations and bugs it caught.
3. **The builders** (future sessions). Each takes 1 build card and
   implements it, with tests, and reports back.

The rule between stages: no signal was allowed to be invented from
knowledge of cybersecurity buyers. Every signal had to come out of a
measurement on the file. That is the opposite of handing the file to a
chatbot and asking "what are the signals", which the assignment warns
against.

Every number in the findings traces to a saved query, so anyone can rerun
it. The explorer caught 2 of its own mistakes before committing, and both
are documented.

## 9. Questions you may be asked, with short answers

**What is the data?** 14.6 million internet scan banners from Shodan, 1 day
of scanning, 1 file.

**How do you get companies out of it?** Group banners by the website domain
they resolve to, keep only domains covering 50 addresses or fewer, and drop
operators, honeypots and anonymous rows. 485,089 businesses result.

**What are the signals?** 4 facts: old software, neglected certificates,
exposed surface, existing protection. Plus disqualifiers.

**What is the most interesting signal?** The negative one. Businesses with a
live service and no protection at all are the first call. Businesses behind
a WAF are a displacement play with a named incumbent.

**How do you know it works?** No sales outcome exists. We hold out proxy
labels, such as known-exploited weaknesses, and measure precision at the
top of the ranking against random and against a trivial baseline.

**Did you use an LLM?** Not for scoring. Reasons: deterministic rules on
structured fields, explainability, cost. Optional summaries only, with cost
per business stated.

**How does it scale?** Offline batch per file, idempotent on re-delivery,
Parquet in object storage, incremental recompute of changed businesses.
We state what breaks at 1,000 files a month.

**What would you do with a second file?** Diff. That is where "right now"
comes from.

**What did you cut?** Email drafting and UI polish, on purpose.

## 10. Numbers worth remembering

| What | Number |
|---|---|
| Lines in the file | 14.6 million |
| Compressed size | 16.4 GB |
| Uncompressed size | 123 GB |
| Scan window | about 1 day, 96 percent in 1 hour |
| Lines tied to a named business | 1.07 million, 7 percent |
| Named businesses | 485,089 |
| Businesses with no security product and a live service | 131,104 |
| Businesses with some security vendor already | 83,779 |
| Share of file belonging to top 5 operators | 62 percent |
| CVE rows that were actually tested, not inferred | under 1 percent |
| Candidate signals found | 17, plus 3 disqualifiers |
| Facts the signals collapse into | 4 |
| Build phases | 10, numbered P0 to P9; P0 to P5 are the submission |

---

## Glossary, alphabetical

- **ASN**: number identifying the owner of a block of addresses.
- **Banner**: what a service replied to the scanner; 1 line of the file.
- **CDN**: content delivery network; servers in front of a website.
- **CPE**: standard name for a software product and version.
- **CVE**: numbered public record of a known software weakness.
- **CVSS / EPSS / KEV**: severity score, exploit probability, list of
  weaknesses exploited in the wild.
- **Domain**: a website name a business owns.
- **DuckDB**: laptop database engine that queries Parquet.
- **Entity resolution**: grouping banners into businesses.
- **EOL**: end of life; unsupported software.
- **Ground truth**: real outcome data; we have none.
- **Honeypot**: decoy server; not a business.
- **Incapsula**: a WAF and CDN vendor; 32 percent of our file.
- **IP address**: numeric address of a machine.
- **JSONL**: 1 JSON object per line.
- **Lift**: how much more common a trait is in a group than overall.
- **Offline scoring**: computing results in advance, not on click.
- **Org**: owner of the address block; the landlord, not the tenant.
- **Parquet**: columnar file format.
- **Peer group**: services of the same type in the same country.
- **Port**: numbered door on a machine.
- **Precision at k**: share of the top k that are good by the proxy.
- **Proxy**: stand-in for ground truth.
- **RAT / C2**: malware and its control servers.
- **Roll-up**: same as entity resolution.
- **Self-signed certificate**: home-made ID that browsers distrust.
- **Shodan**: the scanner that produced the file.
- **Signal**: a measurable fact that changes a business's score.
- **TLS certificate**: the ID a secure website presents.
- **WAF**: web application firewall; a filter in front of a website.
- **zstd**: the compression used on the file.

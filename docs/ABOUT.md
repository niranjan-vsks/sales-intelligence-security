# About this tool

This is a prospecting tool for a cybersecurity sales team. It ranks
businesses by how much visible security exposure they have on the public
internet, tells you whether they already have a security vendor, and shows
you the evidence so you can say on a call why you are calling.

## Where the data comes from

The source is an internet scan: a crawler that knocks on every address
and port it can reach and records what answers. Each answer is a banner:
the software that replied, its version, its certificate, its headers, and
the security products visible in front of it. This tool read 14.6 million
such banners, collected in 1 day, and worked out which ones belong to
which business.

Only banners that resolve to a business's own domain are used. Banners
that belong to a cloud provider, a content delivery network, a hosting
company's shared infrastructure, or a decoy server are set aside. That
leaves 487,133 named businesses.

## What the score means

**Exposure** is a number from 0 to 100. It combines 3 things we can see
from outside:

- **Visibly old software.** Services that announce a version with
  published weaknesses, or software past its end of life.
- **Neglected certificates.** Self-signed, expired, or far older than
  comparable services.
- **Exposed surface.** Remote-admin, file-sharing or database services
  reachable from the internet, Windows internals, and more open services
  than similar businesses have.

Each is scored against peers: businesses in the same country with a
similar number of services. An old certificate counts for more in a group
where everyone else rotates on time.

**Protection present** is shown separately and does not raise the score.
It records what the business already has: a web application firewall, a
known firewall or VPN appliance, an edge platform, or hardening headers.

## The 4 segments

| Segment | Meaning | Sales play |
|---|---|---|
| Untouched | something of theirs answers the internet and no security product is visible | first call |
| Partially covered | an edge platform, VPN or hardening headers, but no dedicated security product | second call |
| Has a vendor | a web application firewall or security appliance is already in front | displacement, with the incumbent named in the evidence |
| Low visible surface | nothing of theirs answered the scan | low priority |

**Priority** is exposure adjusted for segment, and is the default sort.

## Reading an account page

The header gives the score, the rank, and the peer group. The 4 bars show
which facts drive the score. The Why panel lists the top reasons in plain
words; expand any of them to see the exact banners: address, port,
service, time observed, and the first lines of what the service said.
Nothing on the page is inferred by a language model; every line traces to
a banner in the source file.

**Mark as prospect** and **Not a fit** record your judgement. Those
marks are the first real outcome data this tool collects, and future
versions of the ranking will be measured against them.

## Changes between deliveries

When a new scan file arrives, the tool compares it with the previous one
and records events per account: a new service, a certificate that
expired since, a firewall that disappeared. Accounts with recent changes
carry a marker in the list. In this deployment the second delivery is a
simulation built from the first file with known changes planted, used to
prove the comparison works; the page says so wherever it applies.

## What this tool does not do

- It does not scan anyone. It reads a scan file produced by a third
  party.
- It does not say a business was breached or is exploitable. Most
  weaknesses are inferred from version strings; the few that were
  actively tested are marked as such in the evidence.
- It does not write outreach messages.

## For engineers

The design document, data model, evaluation results and build history are
in the repository README linked in the footer.

# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in playlist-forge, please report it
privately rather than opening a public issue — this gives time to investigate
and release a fix before details are public.

To report a vulnerability, contact the maintainer directly via GitHub:
**https://github.com/mwaddell**

Please include as much of the following as you can:

- A description of the vulnerability and its potential impact
- Steps to reproduce it (a minimal example is ideal)
- The affected version/commit
- Any suggested fix or mitigation, if you have one

## What to expect

- Please allow a reasonable amount of time for a response before disclosing
  publicly.
- You'll be credited in the fix/release notes if you'd like, unless you
  prefer to remain anonymous.

## Scope

This project authenticates to Spotify via OAuth (PKCE) and optionally calls
the third-party ReccoBeats API. Vulnerabilities of particular interest
include:

- Anything that could leak or mishandle Spotify OAuth tokens or credentials
- Anything that could cause unintended write actions against a user's
  Spotify account (e.g. bypassing `--dry-run`, unintended playlist
  deletion/modification)
- Dependency vulnerabilities with a realistic exploit path in this project's
  usage

Issues in third-party services this project depends on (Spotify's own API,
ReccoBeats) should be reported to those services directly, not here.

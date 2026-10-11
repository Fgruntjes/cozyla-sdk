# 1. Talk to the Cozyla cloud API, mapped from the decompiled tablet apps

## Status

Accepted

## Context

Cozyla publishes no API for the Calendar 2+ and no third-party client exists.
The tablet is an unrooted Android 14 `user` build, so the apps' local databases under `/data` are unreadable over ADB.
The tablet and the Cozyla+ phone app both sync through the Cozyla cloud (`https://api.cozylacal.com/cal-server/...`).
Calendar events already sync both ways with CalDAV/Google/iCloud, which Home Assistant reaches natively; tasks, chores, rewards, meals and notes have no external sync path.

## Decision

The client talks to the same cloud endpoints the vendor apps use.
Endpoints, payloads and auth are mapped by statically decompiling the vendor-signed APKs pulled from our own tablet, and recorded in `docs/cozyla-cloud-api.md` with the app version they came from.

## Consequences

- Any domain the phone app can manage is reachable without touching the tablet.
- Cozyla can change or block the API at any time; a broken endpoint is fixed by re-decompiling the newer app version.
- Using an undocumented API may conflict with Cozyla's terms of service; users run this at their own risk with their own account.
- Facts that static analysis cannot settle are only confirmed by the live smoke test against a real account.

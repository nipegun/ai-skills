# TryHackMe Rooms to Satisfy a Job Offer

This README is also available in:\
[en-GB](doc/README.en-GB.md), en-US, [es-AR](doc/README.es-AR.md), [es-ES](doc/README.es-ES.md)

This skill turns the requirements in a cyber-security job offer into a tailored TryHackMe training list. By default it searches the bundled room and module catalogues; on request it can rebuild both from TryHackMe's authenticated search before finding direct and supporting matches for the role.

A room is a single hands-on lab. A module is a curated sequence of rooms, published at `https://tryhackme.com/module/<code>`. The report recommends rooms first and then advises the modules that group them, so the reader sees both the individual labs and the learning route through them.

## Current support

The functional implementation supports Debian, Windows and macOS 10.14 or newer. Debian reads Firefox, Chromium, LibreWolf and Epiphany. Windows reads Firefox and compatible legacy Chrome, Edge and Chromium profiles; current `v20` app-bound cookies remain non-exportable by design. macOS 14 or newer uses `os-mac/modern/`, which reads Firefox, Safari, Chrome and Chromium profiles and is validated on Sequoia 15.x. macOS 10.14 through 13.x uses `os-mac/legacy-http/`, which reads Firefox, Chrome and Chromium and is validated on Mojave 10.14.

The generated [room catalogue](thm-rooms/all-rooms.json) and [module catalogue](thm-modules/all-modules.json) contain public data only. Browser cookies, account details, personal progress and job-offer text are never written to them.

## Requirements

- Python 3.13 or newer on Debian, Windows and the modern macOS route; Python 3.10 or newer on the legacy HTTP macOS route.
- For live catalogue refresh only: a logged-in TryHackMe session, the selected platform's Python packages and its documented automation browser requirements.
- For live refresh on Debian only, a project path short enough for Chromium's socket limit; the command says so plainly if it is not.

## Catalogue choice

Every recommendation run asks which source to use unless the request already says so explicitly:

1. **Use the bundled catalogues — default and recommended.** This skips browser access and the two long catalogue managers.
2. **Update and expand both catalogues.** This uses the authorised browser session to recheck all rooms and modules against TryHackMe before matching the vacancy.

In the fast default mode, only the room and module links that survive semantic review are checked before the report is rendered. Any non-200 response is retried once.

## Installation on Debian

This installation is needed only for a live refresh. Run it as the desktop user whose browser contains the TryHackMe session:

```bash
python3 -m pip install -r os-debian/requirements.txt --break-system-packages
```

If Chromium is not installed, install it as `root`:

```bash
apt-get update
apt-get install chromium
```

## Installation on Windows

This installation is needed only for a live refresh. Run it from PowerShell as the desktop user whose browser contains the TryHackMe session:

```powershell
python -m pip install -r .\os-windows\requirements.txt
```

Firefox can remain open while its session is read. Chrome, Edge and Chromium may lock their cookie database while running, and current releases normally use non-exportable `v20` app-bound encryption. The Windows helper reports either condition without exposing cookie data; use a logged-in Firefox profile when that occurs.

## Installation on macOS

This installation is needed only for a live refresh. On macOS 14 or newer, run it as the desktop user whose Firefox, Safari, Chrome or Chromium profile contains the TryHackMe session:

```bash
python3 -m pip install -r os-mac/modern/requirements.txt
```

On macOS 10.14 through 13.x, install from `os-mac/legacy-http/requirements.txt` instead; that route supports Firefox, Chrome and Chromium but not Safari. The browser may remain open. For Chrome or Chromium, keep the login Keychain unlocked and approve Safe Storage access if macOS asks. Passwords and cookies are kept only in process memory.

## Running a live catalogue refresh

These commands are used only for the optional live-refresh mode. From this directory, run both; each opens its own browser session:

```bash
./os-debian/manage_rooms.py --locale en-GB
./os-debian/manage_modules.py --locale en-GB
```

On Windows, use:

```powershell
python .\os-windows\manage_rooms.py --locale en-GB
python .\os-windows\manage_modules.py --locale en-GB
```

On macOS, use:

```bash
./os-mac/modern/manage_rooms.py --locale en-GB
./os-mac/modern/manage_modules.py --locale en-GB
```

On macOS 10.14 through 13.x, replace `modern` with `legacy-http` in both commands.

The first run of each obtains and verifies its complete catalogue. Every later run verifies the stored entries first, fetches the complete live listing, appends newly published rooms or modules and verifies those additions. Entries that disappear from the live listing remain as history but are excluded from recommendations.

If TryHackMe's browser checkpoint cannot finish in a Playwright context, retry with `--headed`. On the modern route under the macOS Seatbelt sandbox, or on the legacy HTTP route, refresh the authenticated page in the source browser and rerun once instead.

## Matching a vacancy

Invoke the skill and paste the complete job-offer text. The model extracts concrete skills and searches both caches with one atomic query per skill, tool or responsibility. The selected platform's `search_rooms.py` and `search_modules.py` report matched tokens and coverage for every candidate; the model then checks that evidence semantically, removes partial coincidences, orders the rooms from foundations to specialist material and labels them Free, Premium or MAX.

Module candidates additionally carry the rooms they contain, their estimated duration, their prerequisites and their next steps, which is what lets the advice name the overlap with the rooms already recommended.

## Persistent HTML report

Every completed recommendation also creates `rooms-to-satisfy-offer.html` in the directory from which the skill was invoked. The report first contains a complete translation of the job offer into the user's language, followed by the same reviewed recommendation tables shown in the console, then the advised modules, then the catalogue gaps.

The report is self-contained, responsive, accessible, printable and compatible with light and dark system themes. It contains no cookies or account data. Running the skill again from the same directory replaces the previous report with the new offer and recommendations.

## Request pacing

During live refresh, catalogue, URL and module-detail requests are sequential. The delay starts at 1.25 seconds, includes jitter, decreases slowly after successful streaks and increases on rate limiting. `Retry-After` is honoured, progress is saved every ten entries and persistent blocking stops the run without discarding completed work. In bundled mode, the final selective check is also sequential, pauses briefly between links and permits exactly one recheck for each non-200 result.

The module search endpoint paginates over a non-deterministic index, so a single pass can return only part of the catalogue. The command repeats the pass until it reaches the total the platform itself reports, and while a pass stays incomplete no cached module is marked as withdrawn.

## Security boundaries

Only during live refresh are cookie stores opened through private snapshots under the workspace's `../_/temp/thm/` directory. The snapshots are removed after use. On the modern macOS route, Safari's binary cookie store is parsed locally; both macOS routes read Chromium Safe Storage through the system Keychain without logging it. Cookies are restricted to TryHackMe domains, never printed and used only to confirm the session, read the catalogues and verify canonical room and module URLs. Bundled mode never reads browser data. The skill does not start machines, solve rooms or bypass paid access.

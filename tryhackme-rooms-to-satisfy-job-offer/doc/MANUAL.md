# User Manual

This MANUAL is also available in:\
[en-GB](MANUAL.en-GB.md), en-US, [es-AR](MANUAL.es-AR.md), [es-ES](MANUAL.es-ES.md).

## Purpose

Use this skill when you have a cyber-security job offer and want a complete, reasoned list of TryHackMe rooms that teach its required skills, plus the modules that group those rooms into a learning route. By default, the skill uses its bundled catalogues; an optional live-refresh mode rebuilds them from TryHackMe before analysing the offer.

## Choose catalogue mode

Unless the request already states a choice, the skill first asks whether to use the bundled catalogues or update and expand both catalogues from TryHackMe. Using the bundled data is the recommended default, needs no browser session and produces the result much faster. A live refresh can take tens of minutes.

In bundled mode, only the links included in the reviewed recommendation are checked before the final report. Any link that does not return HTTP 200 is checked once more. A recommendation confirmed unavailable, such as by HTTP 404 or 410, is removed and reported as a catalogue gap. A repeated rate limit, security checkpoint, server error or transport failure can retain only a previously validated cached entry, and the final response states that the current check was inconclusive.

## Live-refresh setup on Debian

1. Log in to `https://tryhackme.com` with Firefox, Chromium, LibreWolf or Epiphany.
2. Keep the desktop keyring unlocked if the active session is in Chromium.
3. Install the dependencies from `os-debian/requirements.txt`.
4. Invoke `$tryhackme-rooms-to-satisfy-job-offer` and paste the job offer when requested.

When live-refresh mode is selected, the skill automatically runs both catalogue commands. To run them yourself, use:

```bash
./os-debian/manage_rooms.py --locale en-GB
./os-debian/manage_modules.py --locale en-GB
```

They are independent commands and each opens its own browser session, so you can run only one of them when you want to refresh a single catalogue.

## Live-refresh setup on Windows

1. Log in to `https://tryhackme.com` with Firefox. Chrome, Edge and Chromium profiles are also detected, but current `v20` app-bound cookies cannot be exported by another application.
2. Install the dependencies from `os-windows/requirements.txt` with the same desktop user that owns the browser profile.
3. Ensure Chrome, Edge or Chromium is installed as the isolated automation browser.
4. Invoke `$tryhackme-rooms-to-satisfy-job-offer` and paste the job offer when requested.

The equivalent manual commands are:

```powershell
python .\os-windows\manage_rooms.py --locale en-GB
python .\os-windows\manage_modules.py --locale en-GB
```

Firefox may remain open. When diagnosing Chrome, Edge or Chromium with `--browser`, close that browser completely first so Windows can snapshot its cookie database. If the profile then reports `v20` app-bound encryption, use Firefox; the protection deliberately prevents cookie export.

## Live-refresh setup on macOS

1. On macOS 14 or newer, log in to `https://tryhackme.com` with Firefox, Safari, Google Chrome or Chromium. On macOS 10.14 through 13.x, use Firefox, Chrome or Chromium.
2. Install the dependencies from `os-mac/modern/requirements.txt` with the desktop user that owns the browser profile. On macOS 10.14 through 13.x, use `os-mac/legacy-http/requirements.txt` instead.
3. For Chrome or Chromium, keep the login Keychain unlocked and allow Safe Storage access if macOS asks.
4. Invoke `$tryhackme-rooms-to-satisfy-job-offer` and paste the job offer when requested.

The equivalent manual commands are:

```bash
./os-mac/modern/manage_rooms.py --locale en-GB
./os-mac/modern/manage_modules.py --locale en-GB
```

On macOS 10.14 through 13.x, replace `modern` with `legacy-http` in both commands. All source browsers may remain open. Firefox values are read from a private SQLite snapshot, Safari values on the modern route from a private binary-cookie snapshot, and Chrome or Chromium values are decrypted in memory with their Keychain Safe Storage item.

## What happens during room preparation

This section applies only to the optional live-refresh mode.

The command checks each supported browser profile until TryHackMe confirms an authenticated session. It does not consider the mere presence of a cookie sufficient.

If `thm-rooms/all-rooms.json` is missing, the complete room catalogue is collected and validated. If the cache exists, all stored URLs are validated first. The complete live catalogue is then fetched on every run so newly published rooms can be appended and validated immediately.

Rooms absent from the latest live listing are retained with `listed: false` for history and auditing. They are not used by the recommendation search. A room that later returns is marked as listed again and its URL is revalidated.

Every canonical room URL is then checked with a lightweight GET. For a catalogue of approximately 1,300 rooms, a normal complete pass takes roughly 17–30 minutes before network backoff. Progress is persisted every ten rooms, so an interrupted run keeps completed checks.

## What happens during module preparation

`./os-debian/manage_modules.py` prepares `thm-modules/all-modules.json` the same way, but a module is verified by reading its official detail rather than by fetching its page: `https://tryhackme.com/module/<code>` is a single-page application route that answers HTTP 200 for any path, so it proves nothing. The detail endpoint answers HTTP 404 for a module that no longer exists.

On Windows, `python .\os-windows\manage_modules.py` performs the same workflow and uses the same cache contract. On macOS, use the version-specific `manage_modules.py` selected by `os-mac/MACOS.md`.

Each detail read also refreshes the rooms the module contains, its estimated duration, its prerequisites, its next steps and its key learnings. The access tier is derived from the rooms: every room free means the module is Free, and at least one paid room means Premium.

For roughly 170 modules a complete pass takes about four minutes. Progress is persisted every ten modules. A module that fails because of a transient network error keeps its previous verified state instead of disappearing from the advice.

The module search endpoint paginates over a non-deterministic index: consecutive pages overlap and one pass can return only part of the catalogue. The command repeats the pass until it reaches the total the platform reports, and while a pass remains incomplete it does not mark any missing module as withdrawn.

## Visible browser fallback

If a command reports that the security checkpoint could not complete, close the failed process and run that same command with `--headed`:

```bash
./os-debian/manage_modules.py --locale en-GB --headed
```

On a route that uses Playwright, a Chromium window opens. Complete any TryHackMe or Vercel prompt shown there. The imported cookies remain in the temporary isolated context and are discarded when the command exits. The legacy HTTP macOS route does not launch an automation browser.

On Windows the equivalent fallback is:

```powershell
python .\os-windows\manage_modules.py --locale en-GB --headed
```

The modern macOS route prefers Playwright and accepts the same `--headed` fallback outside restricted environments. Under the macOS Seatbelt sandbox it automatically uses a TryHackMe-only HTTPS cookie jar because Chromium cannot register its Mach service; if that transport reports the security checkpoint, refresh an authenticated page in the selected source browser and rerun once. The legacy HTTP route uses the same refresh-and-rerun behaviour.

## Supplying the job offer

Paste the full text, including responsibilities, mandatory skills, desirable skills, platforms, tooling and seniority. Removing sections may hide useful training matches. The skill converts the offer into atomic searches and accepts a candidate only when it has meaningful token coverage or exact evidence; the model still makes the final semantic decision.

The final answer separates:

- Core rooms that directly cover mandatory requirements.
- Role-specific rooms for named tools, platforms and responsibilities.
- Supporting rooms that fill prerequisites or desirable skills.
- Advised modules that group the recommended rooms into a learning route.
- Catalogue gaps for requirements without a defensible match.

Each room recommendation includes the official title, relevance, subscription tier and canonical URL. Each advised module adds its estimated time, how many rooms it contains and which of those rooms were already recommended above. Premium and MAX content is a recommendation only; the skill does not bypass access controls.

## HTML report

After printing the complete tables, the skill creates `rooms-to-satisfy-offer.html` in the directory where it was invoked. Open that file in any modern browser to retain the translated offer, role assessment, catalogue status, recommendation tables, advised modules and uncovered requirements. The module tables always come after the room tables.

In bundled mode, `scripts/verify_recommendations.py` reads the reviewed report data, checks only its canonical TryHackMe room and module links, and retries every non-200 response once before the renderer is run.

The offer is translated completely rather than summarised. Names, products, URLs, currencies, salary figures and list structure are preserved. The report follows the system light or dark theme and includes print-specific formatting. A later run in the same directory replaces the file.

## Manual catalogue options

When live-refresh mode is selected, discovery is automatic on every run of both commands and has no opt-out flag. On Debian use `--browser firefox`, `chromium`, `librewolf` or `epiphany`; on Windows use `--browser firefox`, `chrome`, `edge` or `chromium`; on the modern macOS route use `--browser firefox`, `safari`, `chrome` or `chromium`. The legacy HTTP macOS route omits `safari`. Use `--locale en-GB`, `en-US`, `es-AR` or `es-ES` for command messages.

`--skip-url-validation` in the room command and `--skip-module-details` in the module command exist for an explicitly requested fast refresh. Neither is used by the normal live-refresh workflow: full verification is part of that mode, and without its details a module has no access tier, no duration and no room list, so it cannot be advised.

## Common failures

### No usable session

Open TryHackMe in a supported browser, log in, confirm that an authenticated page works and run the skill again. A stale cookie database is ignored.

### Chromium keyring locked

Unlock the current desktop user's GNOME keyring, or use an authenticated Firefox, LibreWolf or Epiphany profile instead.

### Windows Chromium database locked or app-bound

Close Chrome, Edge or Chromium completely before selecting that browser explicitly. If the next run reports `v20` app-bound encryption, the browser is working as designed and another process cannot export those cookies. Use an authenticated Firefox profile. The skill does not bypass this Windows security boundary.

### macOS Safe Storage unavailable

Run the command as the same desktop user that owns the Chrome or Chromium profile, unlock the login Keychain and approve access if macOS prompts. If the execution environment has no access to the interactive desktop Keychain, use an authenticated Firefox or Safari profile; the skill does not extract browser process memory or change Keychain security settings.

### The workspace path is too deep

Chromium's process-singleton socket cannot exceed 104 characters and the project's temporary directory contributes to it. The command refuses to start with a message naming the offending path; move the project to a shorter absolute path.

### Persistent HTTP 429 responses

The command increases its delay and honours `Retry-After`. If three consecutive entries remain blocked after three retries each, it stops and keeps the saved progress. Wait before resuming; do not reduce the delay to bypass the limit.

### Missing Python package

Run:

```bash
python3 -m pip install -r os-debian/requirements.txt --break-system-packages
```

On Windows run:

```powershell
python -m pip install -r .\os-windows\requirements.txt
```

On macOS run:

```bash
python3 -m pip install -r os-mac/modern/requirements.txt
```

On macOS 10.14 through 13.x, install from `os-mac/legacy-http/requirements.txt` instead.

## Privacy

Both caches contain public metadata and HTTP verification state. They do not contain cookie values, browser history, account data, your own progress through a module's rooms, or the pasted job offer. Temporary cookie-store snapshots are created only under the project temporary directory and removed after the read finishes. On the modern macOS route, Safari values remain in memory only; on both macOS routes, the same is true of Safe Storage and decrypted Chromium cookies.

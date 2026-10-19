# Debian implementation

Read this file only when the skill runs on Debian or a directly compatible Debian-based system.

## Runtime requirements

- Python 3.13 or newer.
- For live catalogue refresh only: a system Chromium executable, the Python packages from `requirements.txt` and at least one logged-in TryHackMe profile in Firefox, Chromium, LibreWolf or Epiphany.

Install the Python dependencies with:

```bash
python3 -m pip install -r os-debian/requirements.txt --break-system-packages
```

If Chromium is missing, install it as `root`; do not use `sudo`:

```bash
apt-get update
apt-get install chromium
```

Chromium's process-singleton socket path cannot exceed 104 characters, and the workspace temporary directory `../_/temp/thm/` contributes to it. `fRequireUsableSocketPath` refuses to launch with a clear message when the project lives at an absolute path deep enough to break that limit; move the project to a shorter path instead of changing the temporary directory.

## Catalogue modes

The skill asks before accessing a browser. The default bundled-catalogue mode skips both preparation commands below and starts at candidate search using the existing JSON caches. Run the room and module preparation sections only after the user explicitly chooses to update and expand both catalogues from TryHackMe.

## Room catalogue preparation

Run from the directory containing `SKILL.md`:

```bash
./os-debian/manage_rooms.py --locale en-GB
```

The command performs these operations in order:

1. Finds unexpired TryHackMe cookies without printing their names or values.
2. Imports one candidate profile into an isolated Chromium context and confirms authentication.
3. Loads and migrates `thm-rooms/all-rooms.json` when it exists.
4. Validates every stored canonical URL with sequential lightweight GET requests.
5. Fetches the complete live catalogue on every run, appends new rooms and marks missing catalogue entries as unlisted without deleting their history.
6. Validates only the newly discovered or relisted URLs, then saves discovery and validation state atomically.

Use `--headed` only when the headless browser cannot complete TryHackMe's security checkpoint. Use `--browser firefox`, `chromium`, `librewolf` or `epiphany` only to diagnose a specific source profile.

The default URL delay starts at 1.25 seconds with random jitter. It decreases slowly after successful streaks, doubles after rate limiting, honours `Retry-After`, retries each URL at most three times and stops after three consecutively blocked rooms. Progress is saved every ten URLs.

## Module catalogue preparation

Modules are curated sequences of rooms, published at `https://tryhackme.com/module/<code>`. They have their own command and their own cache, and it opens its own browser session:

```bash
./os-debian/manage_modules.py --locale en-GB
```

The command performs these operations in order:

1. Finds an authenticated session exactly as the room command does.
2. Loads `thm-modules/all-modules.json` when it exists.
3. Re-reads the official details of every cached module, refreshing its room list, access tier and duration.
4. Fetches the complete live module catalogue on every run, appends new modules and marks missing entries as unlisted without deleting their history.
5. Reads the details of only the newly discovered or relisted modules, then saves discovery and detail state atomically.

Module details come from `/api/v2/modules/data?moduleURL=<code>`, which returns HTTP 404 for a module that no longer exists. That check replaces URL validation for modules, because `https://tryhackme.com/module/<code>` is a single-page application route that answers HTTP 200 for any path and therefore proves nothing.

`--detail-delay` sets the initial pause between detail requests and follows the same adaptive rate limiting as room validation. Use `--skip-module-details` only when the user explicitly asks for it: without the details a module has no access tier, no duration and no room list, so it cannot be advised.

## Candidate search

After extracting job requirements, run one room search with multiple coherent queries:

```bash
./os-debian/search_rooms.py \
  --query "SIEM alert triage" \
  --query "Microsoft Sentinel KQL" \
  --query "incident response" \
  --limit 80
```

Then run the same queries against the module cache:

```bash
./os-debian/search_modules.py \
  --query "SIEM alert triage" \
  --query "Microsoft Sentinel KQL" \
  --query "incident response" \
  --limit 30
```

Use one atomic skill, tool or responsibility per `--query`. Both commands emit matched tokens and coverage as evidence, but remain candidate sets rather than final recommendations. Module candidates additionally carry `roomCodes`, `roomTitles`, `totalTimeMinutes`, `prerequisites` and `nextSteps`, which is what makes it possible to name the overlap with the rooms already recommended. Review every candidate semantically, remove incidental keyword matches and add a concise reason tied to the offer.

## HTML report

After semantic review, create one temporary UTF-8 JSON file with this contract:

```json
{
  "locale": "es-ES",
  "documentTitle": "Salas y módulos de TryHackMe para esta oferta",
  "offerTranslated": "Texto completo de la oferta traducida",
  "roleAssessment": "Evaluación breve del puesto y su seniority",
  "catalogue": {
    "roomCount": 1313,
    "validatedUrlCount": 1313,
    "freeCount": 712,
    "premiumCount": 601,
    "moduleCount": 172
  },
  "sections": [
    {
      "title": "Núcleo CTI",
      "description": "Orden de aprendizaje recomendado",
      "rows": [
        {
          "room": "Intro to Cyber Threat Intel",
          "url": "https://tryhackme.com/room/cyberthreatintel",
          "tier": "free",
          "why": "Fundamentos, estándares y marcos de CTI."
        }
      ]
    }
  ],
  "moduleSections": [
    {
      "title": "Módulos aconsejados",
      "description": "Rutas completas que agrupan las salas anteriores",
      "rows": [
        {
          "module": "Cyber Threat Intelligence",
          "url": "https://tryhackme.com/module/cyber-threat-intelligence",
          "tier": "premium",
          "timeMinutes": 480,
          "roomCount": 8,
          "recommendedRooms": [
            "Intro to Cyber Threat Intel",
            "Threat Intelligence Tools"
          ],
          "why": "Agrupa en orden la formación de CTI que pide la oferta."
        }
      ]
    }
  ],
  "gaps": [
    {
      "requirement": "Definición de PIRs",
      "coverage": "No hay una sala dedicada."
    }
  ]
}
```

Use one row per recommended room and one row per advised module. `tier` accepts `free`, `premium`, `max` or `unknown`. Every room URL must be a canonical `https://tryhackme.com/room/<code>` URL already present in the validated cache, and every module URL a canonical `https://tryhackme.com/module/<code>` URL already present in the module cache.

`moduleSections` is optional and every field inside a module row except `module`, `url`, `tier` and `why` is optional too. `timeMinutes` and `roomCount` must be non-negative integers when present; the renderer prints whole hours above one hour and minutes below it. `recommendedRooms` holds the titles of the rooms already listed in the room tables, so the reader sees the overlap. `catalogue.moduleCount` adds a fifth metric card and is omitted when it is zero.

In bundled-catalogue mode, first check only the links present in this reviewed JSON. The command automatically repeats every non-200 result once:

```bash
python3 scripts/verify_recommendations.py \
  --input /absolute/path/to/report-data.json
```

Review its JSON summary before rendering. Remove a recommendation conclusively unavailable with HTTP 404 or 410 after the second attempt, update module overlaps and catalogue gaps, then check the reduced selection again. For rate limits, security checkpoints, server errors or transport failures, follow the cached-validation rule in `SKILL.md`.

Once the final selection satisfies those rules, run the renderer with the original invocation directory, not the skill directory:

```bash
./os-debian/render_report.py \
  --input /absolute/path/to/report-data.json \
  --output-directory /absolute/original/working-directory
```

The renderer creates or replaces exactly `rooms-to-satisfy-offer.html`. It escapes all input, rejects non-canonical room and module URLs and produces a self-contained responsive document with light, dark and print styles. Module tables are rendered after every room table. Delete the intermediate JSON after success, then link the absolute HTML path in the console response.

## Room cache contract

`thm-rooms/all-rooms.json` uses schema version 2. Version 1 is migrated automatically. Each room contains `code`, `title`, `description`, `url`, `isPremium`, `accessTier`, `difficulty`, `roomType`, `listed`, `firstSeenAt` and `lastSeenAt`. Once URL checks run, a `validation` object contains `checkedAt`, `httpStatus`, `finalUrl` and `valid`.

The root `discoveryState` records new, relisted and no-longer-listed room codes from the latest full catalogue pass. `validationState` records an in-progress or completed URL pass, while `lastFullValidationAt` identifies the last complete validation of all stored rooms. Historical rooms remain in the JSON, but search excludes entries that are unlisted or not successfully validated.

## Module cache contract

`thm-modules/all-modules.json` uses schema version 1. Each module contains `code`, `title`, `description`, `summary`, `url`, `tags`, `difficulty`, `difficultyLevel`, `moduleType`, `isPremium`, `accessTier`, `listed`, `firstSeenAt` and `lastSeenAt`. Once its details are read it also contains `rooms`, `roomCount`, `freeRoomCount`, `paidRoomCount`, `totalTimeMinutes`, `prerequisites`, `nextSteps`, `keyLearnings`, `isPublic` and a `validation` object with `checkedAt`, `httpStatus`, `finalUrl` and `valid`.

Each entry of `rooms` keeps only `code`, `title`, `url`, `isFree`, `roomType` and `order`. The account's own `progress` and `toPay` fields are deliberately discarded, because they describe the logged-in user rather than the module.

The access tier is derived from the room list: every room free means `free`, at least one paid room means `premium`, and an empty room list leaves the tier as reported by the search endpoint. The root `discoveryState` mirrors the room cache, and `detailState` records an in-progress or completed detail pass while `lastFullDetailAt` identifies the last complete pass over all stored modules.

Neither cache must ever contain cookie values, account details, copied browser databases or job-offer text. The generated HTML intentionally contains the translated offer because it is the user's requested persistent report.

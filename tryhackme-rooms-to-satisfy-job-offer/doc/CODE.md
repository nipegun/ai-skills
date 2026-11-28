# Codebase Guide

This CODE is also available in:\
[en-GB](CODE.en-GB.md), en-US, [es-AR](CODE.es-AR.md) , [es-ES](CODE.es-ES.md).

## Index

1. [Architecture and design decisions](#architecture-and-design-decisions)
2. [Module map](#module-map)
3. [Key symbol index](#key-symbol-index)
4. [Main call paths](#main-call-paths)
5. [Command map](#command-map)
6. [Impact analysis](#impact-analysis)
7. [Extension points](#extension-points)

## Architecture and design decisions

The skill entrypoint owns a platform-neutral catalogue choice. The default path reads the bundled caches, performs candidate search and semantic review, then checks only the canonical links that survived into the reviewed recommendation. The optional live-refresh path routes to the operating-system implementation, acquires an authorised session and rebuilds both catalogues before the same search and review stages. This makes the common fast path independent of browser storage and keeps every platform's credential logic confined to an explicit refresh.

The skill separates three concerns: acquiring authorised session cookies, using those cookies through the selected platform transport, and ranking public cached metadata. This boundary keeps browser storage details out of the TryHackMe client and keeps account credentials out of recommendation logic.

Direct HTTP calls to the current TryHackMe application encounter its JavaScript security checkpoint. `TryHackMeBrowserClient` therefore launches an isolated system Chromium through Playwright, imports only TryHackMe cookies and performs same-origin browser `fetch` calls. Firefox, LibreWolf and Epiphany cookies are plaintext SQLite values; Chromium `v10` and `v11` values are decrypted locally using Chromium's Linux algorithm and Secret Service. Chromium's process-singleton socket cannot exceed 104 characters, and the workspace temporary directory contributes to it, so `fRequireUsableSocketPath` refuses to launch with a diagnosable message instead of the opaque browser crash that a deep project path would otherwise produce.

Windows keeps its credential logic under `os-windows/`. Firefox is read through SQLite's backup API and accepts expiry expressed in seconds or milliseconds. Compatible Chrome, Edge and Chromium profiles use current-user DPAPI plus AES-GCM for legacy `v10`/`v11` values. `v20` app-bound values are rejected explicitly because Windows binds their decryption to the browser application; the implementation does not inject into a browser or elevate to bypass that boundary. The isolated client locates an installed Chrome, Edge or Chromium executable and otherwise reuses the same public catalogue, cache and report contracts as Debian.

`os-mac/MACOS.md` routes macOS 14 or newer to `os-mac/modern/` and macOS 10.14 through 13.x to `os-mac/legacy-http/`. Both routes read Firefox from private SQLite snapshots and decrypt Chrome or Chromium `v10` values with Safe Storage, PBKDF2-HMAC-SHA1, 1,003 iterations and AES-128-CBC. The modern route additionally parses Safari's bounded `Cookies.binarycookies` records. Its client prefers an isolated Playwright context, but detects the macOS Seatbelt sandbox—which denies Chromium's Mach rendezvous service—and then uses an in-memory `CookieJar` whose requests and redirects are restricted to TryHackMe HTTPS domains. The legacy HTTP route always uses that restricted transport. Every route verifies the session through `/api/v2/users/self`; Safe Storage and plaintext cookies are never logged or persisted.

The two content types are deliberately two commands with two caches. A room is a single lab; a module is a curated sequence of rooms. They are verified by different mechanisms and their preparation costs differ by an order of magnitude, so coupling them would force a caller who wants one to pay for the other. Each command opens its own authenticated session and owns its own cache file.

Caches are an operational boundary. Room schema 2 and module schema 1 store normalised public metadata, verification status and discovery history, never session or account data. The module detail deliberately drops the platform's `progress` and `toPay` fields because they describe the logged-in user rather than the content. Both merges are unions: new entries are appended, returning entries are relisted and missing entries are retained with `listed: false`. Writes are staged beneath the project temporary directory, flushed, synchronised and atomically replaced.

Rooms and modules are verified differently because the platform answers differently. A room is validated with a lightweight GET of its canonical URL. A module cannot be, because `https://tryhackme.com/module/<code>` is a single-page application route that returns HTTP 200 for any path; `/api/v2/modules/data?moduleURL=<code>` returns HTTP 404 for a module that no longer exists, so the detail read is both the enrichment and the existence proof.

The module search endpoint paginates over a non-deterministic index: consecutive pages overlap and a single pass can return only part of the catalogue, with the shortfall varying between otherwise identical runs. `mFetchModuleCatalogue` therefore repeats the pass and unions the results until it reaches the total the endpoint itself reports, and returns that total so `fDiscoverModules` can decide whether the pass was complete. An incomplete pass never marks a cached module as withdrawn, and a transient detail failure never demotes a module a previous pass verified, because search accepts only verified modules and either event would otherwise silently delete real content from the advice.

Neither catalogue is small enough to inject into a model context. `search_rooms.py` normalises common technical variants, applies BM25-style ranking and exact-phrase boosts, and rejects partial matches without meaningful token coverage. `search_modules.py` reuses that scoring but builds its documents from the module's title, summary, description, key learnings, tags and the titles of the rooms it contains, which is what lets a module match the vocabulary of the offer through its constituent labs. Each accepted query emits its matched tokens, coverage and exact-phrase evidence. The skill then performs the semantic decision against the original offer, because deterministic text ranking alone cannot decide whether content genuinely teaches a requirement.

The reviewed result crosses a second explicit boundary before persistence. In bundled mode, the platform-neutral `scripts/verify_recommendations.py` extracts only the canonical room and module URLs from the reviewed report JSON, checks them sequentially without browser cookies and retries every non-200 result exactly once. Content conclusively unavailable with HTTP 404 or 410 is removed by the skill before rendering. Rate limits, security checkpoints, server errors and transport failures are inconclusive and can retain only a cache entry with a previous successful validation, with disclosure. `render_report.py` then validates the small report JSON contract, escapes every value and generates a self-contained `rooms-to-satisfy-offer.html` in the invocation directory. Module tables render after every room table because the advice is about learning order over content the reader has already seen. The intermediate JSON is temporary; only the user-requested HTML retains the translated offer.

All network loops are sequential. Adaptive delay, jitter, bounded retries, `Retry-After` handling, incremental saves and a persistent-block stopping condition limit platform load and make long runs resumable.

## Module map

| Module | Path | Responsibility | Depends on | Used by |
|---|---|---|---|---|
| Skill entrypoint | `SKILL.md` | Routes by operating system and defines the recommendation workflow | `os-debian/DEBIAN.md`, `os-windows/WINDOWS.md`, `os-mac/MACOS.md` | Skill loader |
| Room operations | `os-debian/manage_rooms.py` | Room CLI, migration, validation-first discovery, cache union and session orchestration | `browser_sessions.py`, `tryhackme_client.py`, `i18n/*.json` | `SKILL.md`, `manage_modules.py`, operator |
| Module operations | `os-debian/manage_modules.py` | Module CLI, detail-first refresh, discovery, cache union and detail state | `manage_rooms.py`, `tryhackme_client.py` | `SKILL.md`, `search_modules.py`, operator |
| Browser sessions | `os-debian/browser_sessions.py` | Discovers profiles, snapshots SQLite stores and decrypts Chromium values | SQLite, SecretStorage, cryptography | `manage_rooms.py` |
| TryHackMe client | `os-debian/tryhackme_client.py` | Browser checkpoint, authentication, room and module pagination, normalisation and lightweight GETs | Playwright, system Chromium | `manage_rooms.py`, `manage_modules.py` |
| Room search | `os-debian/search_rooms.py` | Ranks valid cached rooms for extracted offer requirements | `manage_rooms.py`, `all-rooms.json` | `SKILL.md`, `search_modules.py` |
| Module search | `os-debian/search_modules.py` | Ranks verified cached modules using their own text and their room titles | `manage_modules.py`, `search_rooms.py`, `all-modules.json` | `SKILL.md` |
| Selective recommendation verifier | `scripts/verify_recommendations.py` | Checks only reviewed canonical room and module links and retries a non-200 result once | Report JSON, public TryHackMe links | `SKILL.md` |
| HTML renderer | `os-debian/render_report.py` | Validates reviewed report data and renders the persistent responsive report | `manage_rooms.py`, `i18n/*.json` | `SKILL.md` |
| Windows implementation | `os-windows/*.py` | Mirrors the catalogue, search and report workflows with Windows browser discovery, DPAPI/AES-GCM and Windows executable selection | Windows browser profiles, SQLite, DPAPI, Playwright | `SKILL.md`, operator |
| macOS routing | `os-mac/MACOS.md` | Selects the documented implementation by supported version family and transport capability | macOS version | `SKILL.md`, operator |
| Modern macOS implementation | `os-mac/modern/*.py` | Adds Safari binary-cookie discovery and a Playwright-first client with a TryHackMe-only Seatbelt fallback | macOS browser profiles, SQLite, Safari binary cookies, Keychain, cryptography, Playwright | `os-mac/MACOS.md`, operator |
| Legacy HTTP macOS implementation | `os-mac/legacy-http/*.py` | Mirrors the workflows with Firefox/Chromium profile discovery, Keychain/AES-CBC and a domain-restricted HTTP transport | macOS browser profiles, SQLite, Keychain, cryptography | `os-mac/MACOS.md`, operator |
| Localisation | `i18n/*.json` | Contains command-line and report strings for four locales | JSON | `Localiser` |
| Room cache | `thm-rooms/all-rooms.json` | Stores public schema-versioned room catalogue and validation data | TryHackMe catalogue | Room manager and searcher |
| Module cache | `thm-modules/all-modules.json` | Stores public module catalogue, room lists, durations and detail verification | TryHackMe module search and detail endpoints | Module manager and searcher |

## Key symbol index

| Symbol | File:line | Purpose |
|---|---|---|
| `fDiscoverCookieStores` | `os-debian/browser_sessions.py:65` | Finds supported native and sandboxed browser stores |
| `fGetChromiumSafeStoragePassword` | `os-debian/browser_sessions.py:171` | Retrieves the current Chromium encryption secret without logging it |
| `fDecryptChromiumCookie` | `os-debian/browser_sessions.py:215` | Decrypts Linux Chromium `v10`/`v11` cookie values |
| `fFindSessionCandidates` | `os-debian/browser_sessions.py:341` | Builds sanitised candidate profiles with unexpired TryHackMe cookies |
| `fDiscoverCookieStores` | `os-windows/browser_sessions.py` | Finds Firefox, Chrome, Edge and Chromium profile stores on Windows |
| `fWindowsDpapiUnprotect` | `os-windows/browser_sessions.py` | Decrypts current-user DPAPI blobs without logging their contents |
| `fReadChromiumMasterKey` | `os-windows/browser_sessions.py` | Reads a compatible Chromium AES key from `Local State` |
| `fDecryptChromiumCookie` | `os-windows/browser_sessions.py` | Decrypts legacy DPAPI or `v10`/`v11` AES-GCM values and rejects `v20` |
| `fGeckoExpiryToUnix` | `os-windows/browser_sessions.py` | Normalises Firefox seconds and milliseconds before Playwright import |
| `fReadMacKeychainPassword` | `os-mac/legacy-http/browser_sessions.py` | Reads Chrome or Chromium Safe Storage without logging it |
| `fDecryptChromiumCookie` | `os-mac/legacy-http/browser_sessions.py` | Decrypts macOS Chromium `v10` AES-CBC values and strips the host digest |
| `fRequireTryHackMeUrl` | `os-mac/legacy-http/tryhackme_client.py` | Prevents authenticated macOS requests or redirects from leaving TryHackMe |
| `fReadSafariCookies` | `os-mac/modern/browser_sessions.py` | Parses bounded Safari records and retains only unexpired TryHackMe cookies |
| `fCanLaunchMacBrowser` | `os-mac/modern/tryhackme_client.py` | Selects the restricted HTTPS fallback when the `CODEX_SANDBOX` environment variable reports Seatbelt |
| `fRequireTryHackMeUrl` | `os-mac/modern/tryhackme_client.py` | Keeps fallback requests and redirects on TryHackMe HTTPS hosts |
| `AdaptiveRateLimiter` | `os-debian/tryhackme_client.py:112` | Controls sequential request timing and backoff |
| `fRequireUsableSocketPath` | `os-debian/tryhackme_client.py:154` | Rejects a workspace path too deep for Chromium's singleton socket |
| `fNormaliseRoom` | `os-debian/tryhackme_client.py:269` | Maps changing API record keys into stable room metadata |
| `fExtractModuleCode` | `os-debian/tryhackme_client.py:398` | Reads a module code from `moduleURL`, a `/module/` path or a slug |
| `fNormaliseModule` | `os-debian/tryhackme_client.py:442` | Maps one module search record into stable module metadata |
| `fFindModuleRecordList` | `os-debian/tryhackme_client.py:499` | Finds the module-like list in a version-tolerant payload |
| `fNormaliseModuleRoom` | `os-debian/tryhackme_client.py:528` | Keeps a module's room fields while discarding account progress |
| `fNormaliseModuleDetail` | `os-debian/tryhackme_client.py:551` | Derives rooms, tier, duration, prerequisites and key learnings |
| `TryHackMeBrowserClient.mVerifySession` | `os-debian/tryhackme_client.py:763` | Confirms imported cookies through the authenticated user endpoint |
| `TryHackMeBrowserClient.mFetchCatalogue` | `os-debian/tryhackme_client.py:783` | Paginates and deduplicates every room returned by the catalogue |
| `TryHackMeBrowserClient.mFetchModuleCatalogue` | `os-debian/tryhackme_client.py:868` | Repeats passes over the unstable module index until its total is met |
| `TryHackMeBrowserClient.mFetchModuleData` | `os-debian/tryhackme_client.py:960` | Reads one module's official detail and proves whether it still exists |
| `fMigrateCache` | `os-debian/manage_rooms.py:122` | Migrates schema 1 rooms to discovery-aware schema 2 |
| `fMergeCatalogue` | `os-debian/manage_rooms.py:234` | Unions live discovery with cached history and reports changes |
| `fDiscoverCatalogue` | `os-debian/manage_rooms.py:408` | Fetches every live catalogue page on each run |
| `fValidateCatalogueUrls` | `os-debian/manage_rooms.py:472` | Validates all rooms or only newly discovered room codes |
| `fMergeModuleCatalogue` | `os-debian/manage_modules.py:161` | Unions module discovery and keeps listing state when a pass is partial |
| `fDiscoverModules` | `os-debian/manage_modules.py:248` | Runs module discovery and decides whether the pass was complete |
| `fApplyModuleDetail` | `os-debian/manage_modules.py:314` | Stores detail metadata and shields verified modules from transient failures |
| `fFetchModuleDetails` | `os-debian/manage_modules.py:370` | Reads all or selected module details with adaptive rate limiting |
| `fRankRooms` | `os-debian/search_rooms.py:229` | Produces a compact evidence-backed room candidate set |
| `fPrepareModuleDocuments` | `os-debian/search_modules.py:44` | Builds module documents from module text plus contained room titles |
| `fRankModules` | `os-debian/search_modules.py:92` | Produces module candidates carrying rooms, duration and ordering data |
| `fExtractRecommendationUrls` | `scripts/verify_recommendations.py:94` | Extracts and deduplicates only reviewed canonical room and module links |
| `fCheckUrl` | `scripts/verify_recommendations.py:204` | Checks one link and performs exactly one recheck after a non-200 result |
| `fValidateCanonicalUrl` | `os-debian/render_report.py:377` | Restricts report links to canonical room or module URLs |
| `fFormatDuration` | `os-debian/render_report.py:588` | Prints whole hours above an hour and minutes below it |
| `fRenderModuleTable` | `os-debian/render_report.py:656` | Renders the advised-module table with its rooms-included column |
| `fBuildHtml` | `os-debian/render_report.py:739` | Escapes reviewed data and builds the self-contained HTML document |

## Main call paths

### Catalogue mode selection

The model asks for bundled or live-refresh mode → bundled is presented first and is the default → bundled confirms both cache files are readable and skips session acquisition → live refresh routes by operating system and runs both preparation commands.

### Live room catalogue preparation

`manage_rooms.fMain` → `fOpenAuthenticatedClient` → `fLoadCache`/`fMigrateCache` → full `fValidateCatalogueUrls` → `fDiscoverCatalogue` → `mFetchCatalogue` → `fMergeCatalogue` → `fSaveCache` → selected validation of new or relisted room codes.

### Live module catalogue preparation

`manage_modules.fMain` → `fOpenAuthenticatedClient` → `fLoadModuleCache` → full `fFetchModuleDetails` → `fDiscoverModules` → `mFetchModuleCatalogue` (repeated passes) → `fMergeModuleCatalogue` with the completeness flag → `fSaveModuleCache` → selected `fFetchModuleDetails` for new or relisted module codes.

### Live session acquisition

`fFindSessionCandidates` → platform `fDiscoverCookieStores` → private snapshot → `fReadGeckoCookies`, `fReadSafariCookies` or `fReadChromiumCookies` → platform decryption when needed (Secret Service on Debian, DPAPI/AES-GCM on Windows, Keychain/AES-CBC on macOS) → isolated Playwright context, or the TryHackMe-only HTTP jar on the modern route under Seatbelt and always on the legacy HTTP route → `/api/v2/users/self`.

### Live room URL validation

`fValidateCatalogueUrls` → `AdaptiveRateLimiter.mWait` → `TryHackMeBrowserClient.mQuickGet` → success/backoff accounting → attach `validation` → `fSaveCache` every ten rooms → final atomic save.

### Module detail verification

`fFetchModuleDetails` → `AdaptiveRateLimiter.mWait` → `mFetchModuleData` → `fNormaliseModuleDetail` → `fApplyModuleDetail` (transient failures keep the previous verified state) → `fSaveModuleCache` every ten modules → final atomic save.

### Job-offer recommendation

The model extracts atomic requirements → calls `search_rooms.fMain` with repeated queries → `fLoadCache` → `fPrepareDocuments` → `fDocumentFrequencies` → `fRankRooms` → the same queries reach `search_modules.fMain` → `fPrepareModuleDocuments` → `fRankModules` → semantic review by the model → grouped room recommendation followed by module advice with official links, tiers and durations.

### Persistent report

The model translates the full offer → creates the temporary reviewed report JSON → in bundled mode, `verify_recommendations.fMain` → `fExtractRecommendationUrls` → sequential `fCheckUrl` with one recheck when needed → the model removes content confirmed unavailable, applies the cached-validation rule to inconclusive failures and updates overlaps and gaps → `render_report.fMain` → `fLoadReport` → canonical-URL and schema validation for rooms and modules → `fBuildHtml` → room tables, then `fRenderModuleTable` for each module section, then gaps → write `rooms-to-satisfy-offer.html` in the original invocation directory → remove the temporary JSON → link the report and state the catalogue mode in the console response.

## Command map

| Command | Handler | File |
|---|---|---|
| `./os-debian/manage_rooms.py` | `fMain` | `os-debian/manage_rooms.py:654` |
| `./os-debian/manage_rooms.py --headed` | `fMain` with visible Playwright | `os-debian/manage_rooms.py:654` |
| `./os-debian/manage_modules.py` | `fMain` | `os-debian/manage_modules.py:545` |
| `./os-debian/manage_modules.py --skip-module-details` | `fMain` without `fFetchModuleDetails` | `os-debian/manage_modules.py:545` |
| `./os-debian/search_rooms.py --query …` | `fMain` → `fRankRooms` | `os-debian/search_rooms.py:295` |
| `./os-debian/search_modules.py --query …` | `fMain` → `fRankModules` | `os-debian/search_modules.py:171` |
| `python3 scripts/verify_recommendations.py --input …` | `fMain` → `fCheckUrl` | `scripts/verify_recommendations.py:273` |
| `./os-debian/render_report.py --input … --output-directory …` | `fMain` → `fBuildHtml` | `os-debian/render_report.py:815` |
| `python .\os-windows\manage_rooms.py` | `fMain` | `os-windows/manage_rooms.py` |
| `python .\os-windows\manage_modules.py` | `fMain` | `os-windows/manage_modules.py` |
| `python .\os-windows\search_rooms.py --query …` | `fMain` → `fRankRooms` | `os-windows/search_rooms.py` |
| `python .\os-windows\search_modules.py --query …` | `fMain` → `fRankModules` | `os-windows/search_modules.py` |
| `python .\os-windows\render_report.py --input … --output-directory …` | `fMain` → `fBuildHtml` | `os-windows/render_report.py` |
| `./os-mac/modern/manage_rooms.py` | `fMain` | `os-mac/modern/manage_rooms.py` |
| `./os-mac/modern/manage_modules.py` | `fMain` | `os-mac/modern/manage_modules.py` |
| `./os-mac/modern/search_rooms.py --query …` | `fMain` → `fRankRooms` | `os-mac/modern/search_rooms.py` |
| `./os-mac/modern/search_modules.py --query …` | `fMain` → `fRankModules` | `os-mac/modern/search_modules.py` |
| `./os-mac/modern/render_report.py --input … --output-directory …` | `fMain` → `fBuildHtml` | `os-mac/modern/render_report.py` |
| `./os-mac/legacy-http/manage_rooms.py` | `fMain` | `os-mac/legacy-http/manage_rooms.py` |
| `./os-mac/legacy-http/manage_modules.py` | `fMain` | `os-mac/legacy-http/manage_modules.py` |
| `./os-mac/legacy-http/search_rooms.py --query …` | `fMain` → `fRankRooms` | `os-mac/legacy-http/search_rooms.py` |
| `./os-mac/legacy-http/search_modules.py --query …` | `fMain` → `fRankModules` | `os-mac/legacy-http/search_modules.py` |
| `./os-mac/legacy-http/render_report.py --input … --output-directory …` | `fMain` → `fBuildHtml` | `os-mac/legacy-http/render_report.py` |

External GET routes are `/api/v2/users/self`, `/api/v2/hacktivities/extended-search` for both `kind=rooms` and `kind=modules`, `/api/v2/rooms/tasks` for missing official descriptions, `/api/v2/modules/data` for module details and canonical `/room/<code>` and `/module/<code>` pages. No endpoint is modified.

## Impact analysis

| Component changed | Direct effects | Required documentation updates |
|---|---|---|
| Browser paths or database schema | Session discovery for one or more browsers | Browser-store sections in `DEBIAN.md` or `WINDOWS.md`, README and MANUAL variants |
| Cookie decryption | Chromium authentication and credential-handling risk | Architecture, privacy and dependency sections |
| Temporary directory path | Chromium launch on deep project paths | Socket-limit notes in `DEBIAN.md` and MANUAL variants |
| Room API normalisation or cache schema | Discovery history, every cached room and search eligibility | Room cache contract, symbol index and migration handling |
| Module normalisation or detail parsing | Module tier, duration, room list and advice eligibility | Module cache contract and module advice rules |
| Module pagination or completeness rule | Catalogue coverage and whether modules are marked unlisted | Pagination notes in `DEBIAN.md`, README and MANUAL variants |
| Request pacing | Catalogue duration, verification time and block risk | Timing and troubleshooting guidance |
| Ranking algorithm | Candidate recall for rooms and modules alike | Recommendation flow and manual behaviour |
| Catalogue-mode choice or selective verifier | Default latency, browser access and final-link handling | `SKILL.md`, all platform guides, README, MANUAL and CODE variants |
| Report JSON or HTML layout | Persistent output, accessibility and translated-offer storage | Report contract and all user-documentation variants |
| i18n keys | All visible command and report messages | Four locale JSON files together |

## Extension points

### Add an operating system

Create a dedicated `os-<platform>/` implementation, add its operating guide and update the routing section of `SKILL.md`. Reuse the public cache schemas and recommendation contract; do not place platform-specific credential logic in shared files.

### Add a Windows browser

Add its profile paths to `os-windows/browser_sessions.py`, reuse an existing reader only when its SQLite and encryption contracts match, and assign a deterministic priority. App-bound formats must remain a documented stop condition unless the browser vendor provides a supported export interface; do not add injection, elevation or process-memory extraction.

### Add a Debian browser

Add its profile globs to `fDiscoverCookieStores`, implement a reader only if its SQLite/encryption format differs and assign a deterministic priority. Keep errors sanitised and never include cookie names or values in output.

### Adapt a TryHackMe payload change

Extend the tolerant key candidates in `fExtractRoomCode`, `fExtractPremium`, `fNormaliseRoom`, `fExtractModuleCode` or `fNormaliseModuleDetail`. Increment `cSchemaVersion` or `cModuleSchemaVersion` only when the persisted JSON contract changes, then add explicit migration or force a clean catalogue replacement.

### Add a locale

Create one complete JSON file under `i18n/`, add the locale to `cLocales` in `manage_rooms.py` and preserve alphabetical display order. `en-GB.json` remains the fallback source of truth. Counted strings come in singular and plural pairs; add both.

### Tune recommendation retrieval

Modify `fTokenise` or `fScoreDocument` while keeping both search outputs as candidates rather than conclusions. For modules, `fPrepareModuleDocuments` decides which text represents a module; changing its weighting changes recall without touching the shared scorer. Semantic relevance, learning order and catalogue gaps remain decisions made by the skill against the full offer text.

### Extend the HTML report

Add optional reviewed fields to `fLoadReport`, escape them in `fBuildHtml` or `fRenderModuleTable` and document the schema change in `DEBIAN.md`. Keep the offer first, keep module tables after room tables, retain console parity, avoid external assets and preserve responsive table containers. Verify horizontal overflow at 320, 360, 390, 412 and 430 pixels in both themes after any layout change.

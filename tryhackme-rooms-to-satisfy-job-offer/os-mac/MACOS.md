# macOS implementation routing

Read this file when the skill runs on macOS. Determine the installed version with `sw_vers -productVersion`, then select an implementation documented below.

## Implemented routes

- On macOS 14 or newer, read [modern/MODERN.md](modern/MODERN.md) and use `./os-mac/modern/` as the helper prefix.
- On macOS 10.14 through 13.x, read [legacy-http/LEGACY-HTTP.md](legacy-http/LEGACY-HTTP.md) and use `./os-mac/legacy-http/` as the helper prefix.
- macOS releases older than 10.14 are not supported.

The directories are named after their transport capabilities rather than individual macOS releases. The modern route is validated on Sequoia 15.x and the legacy HTTP route on Mojave 10.14; keep the version boundary above unless the runtime requirements or platform tests establish a different one.

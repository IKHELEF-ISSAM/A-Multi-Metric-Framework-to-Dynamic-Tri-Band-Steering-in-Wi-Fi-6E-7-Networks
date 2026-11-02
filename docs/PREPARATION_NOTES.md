# Source-release preparation

## Input and exclusions

Prepared from the uploaded `Multi_optimization_github.zip` working tree.
The release contains active source, assets, dependency manifests, an English
README, examples and offline tests. Original and nested Git histories were
excluded, so historical secrets and obsolete versions are not published.

Also excluded: all Python virtual environments, `node_modules`, dependency
binaries, SQLite databases/WAL/SHM files, live `.env`, steering-state JSON,
old nested ZIP, duplicate backend copy and `_V1.py` backend files. The case-only
duplicate `scenes/steering` was omitted; the route imports `scenes/Steering`.
`LineChart_rssi_old.jsx` was retained because the RSSI2 route still imports it.

The uploaded `.env` contains legacy authentication settings. It is not in
this release. If that original file or Git history has previously been shared,
replace any credentials it exposed; this preparation cannot revoke them.

## Changes

- Backend package renamed from `openwisp_demo` to `wifi_steering`; CLI imports,
  API subprocess arguments and documentation updated. Active imports now use
  the existing `OpenWrtClient` class directly.
- Active backend kept at the repository root, dashboard moved to `frontend/`.
- Examples use fictitious MACs rather than copied station identifiers.
- Per-device sample rules anonymized; no original live rules/state published.
- CLI direct SSH target, port and key now come from `.env`, rather than a
  hard-coded root/AP target that bypassed the supplied connection settings.
- SSH host-key checks enabled consistently.
- CLI `--apply` and dashboard process start now require `BPI_ALLOW_CHANGES=true`.
  The existing client-level action gates are retained.
- API defaults to loopback with debug disabled; local dashboard CORS origins
  are explicit. This does not add an authentication layer.
- Station-metrics API reads the configured database rather than another
  hard-coded SQLite filename. API rule path defaults to the controller rule path.
- Frontend API URLs centralized with a same-origin Vite-proxy default.
- Original decision/scoring algorithms retained. An inaccurate cooldown
  comment corrected to match the existing 60-second floor.
- Upstream template license and attribution retained. No new license granted
  for original project code.

## Verification

- Active Python modules compile successfully.
- Five offline tests pass: SQLite initialization, rule-file creation,
  client dry-run without SSH, CLI application gating and API start gating.
- Python dependencies for offline checks were read from the uploaded environment;
  no AP was contacted, no service deployed and no steering action executed.
- The normal Vite/SWC production build could not be completed in this execution
  environment: the uploaded native SWC module requests a Linux mount table
  unavailable here. An alternate esbuild-based verification also encountered
  a native dependency's `/proc` requirement. This is not a successful build.
- JavaScript/JSX parsing and local import resolution are checked separately.
- Run `npm ci && npm run build` on your Linux development machine before
  treating the frontend production build as verified.

Live telemetry, API integration with hardware, client BSS-TM acceptance,
arbitrary AP interface names and radio reconfiguration have not been tested.

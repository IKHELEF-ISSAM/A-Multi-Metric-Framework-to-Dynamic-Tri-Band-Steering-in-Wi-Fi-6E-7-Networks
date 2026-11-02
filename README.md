# Multi-Metric Wi-Fi Client Steering

A research prototype for monitoring and steering clients between the 2.4, 5
and 6 GHz radios of an OpenWrt access point. The Python controller communicates
**directly with OpenWrt over SSH**. A React dashboard displays measurements,
per-device rules, scores and steering diagnostics.

**OpenWISP is not required.** The historical Python package name has been
replaced with `wifi_steering` throughout the active backend and subprocess commands.

## What the project does

- Collects radio and station information using `iw`, `hostapd_cli`, UCI and
  network-interface counters on the AP.
- Stores telemetry, association snapshots and control history in SQLite.
- Evaluates candidate bands using client count, RSSI, airtime, throughput and
  transmit-power criteria, with per-device eligibility, preferences and weights.
- Produces steering decisions and BSS Transition Management requests.
- Provides a Flask API and a React/Vite dashboard for configuration, monitoring
  and browser-side measurement exports.

This is a single-AP, multi-radio experimental implementation. A high candidate
score, an issued steering request and a confirmed client band change are
different events; client support and association state affect the outcome.

## Repository layout

| Path | Purpose |
| --- | --- |
| `wifi_steering/client.py` | Direct OpenWrt SSH telemetry client |
| `wifi_steering/controller.py` | Scoring, constraints, decisions and BSS-TM command construction |
| `wifi_steering/cli.py` | Database initialization, collection, control and CSV export |
| `wifi_steering/api.py` | Dashboard API and steering-process management |
| `wifi_steering/config.py` | Environment configuration |
| `wifi_steering/device_rules.py` | Persistent per-device rules |
| `wifi_steering/storage.py` | SQLite schema and persistence |
| `frontend/` | React dashboard, Vite configuration and npm lockfile |
| `config/device_rules.example.json` | Anonymized examples adapted from the supplied experiment |
| `.env.example` | Local OpenWrt, API and scoring configuration template |
| `docs/OPENWRT_SETUP.md` | AP prerequisites and radio mapping |
| `docs/CONFIGURATION.md` | Parameters, rules and metric interpretation |
| `docs/PREPARATION_NOTES.md` | Changes and verification performed for this source release |
| `tests/test_offline.py` | Checks that do not connect to an access point |

## Requirements

- Linux controller host with Python **3.10 or newer**, pip, venv and an OpenSSH client.
- Node.js **20.19+ or 22.12+** supported by the included Vite 7 configuration,
  and npm. Use a maintained Node release satisfying those requirements.
- An OpenWrt AP accessible by SSH key authentication, with `iw`, UCI and
  `hostapd_cli`, and a hostapd/wpad build supporting BSS transition requests.
- Clients supporting the destination band and, for BSS-TM, the relevant client
  capabilities. Three configured radios do not imply every client supports 6 GHz.

The original testbed used a Banana Pi BPI-R4. The active controller still has
the testbed interface convention `phy0.0-ap0`, `phy0.1-ap0`, `phy0.2-ap0`
in some discovery and parsing paths. Changing `.env` mappings alone is not
sufficient to guarantee support for arbitrary interface names; see the AP guide.

## 1. Install the Python backend

Run all backend commands from the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with the AP address, SSH user/key and verified interface/UCI mapping.
`192.0.2.1` is a documentation placeholder, not a working AP address.
`BPI_ALLOW_CHANGES=false` is the default.

Establish SSH trust manually and verify the AP fingerprint, using your actual
connection settings:

```bash
ssh -i /absolute/path/to/your/key -p 22 root@YOUR_AP_ADDRESS
```

SSH operations enforce known-host checking. An empty `BPI_SSH_KEY` uses the
standard SSH agent/default-key configuration. Password-only access is not used
by the non-interactive collector.

## 2. Configure device rules

The controller creates `device_rules.json` if it is absent. Start with an empty
file and configure rules through the dashboard, or copy the example:

```bash
cp config/device_rules.example.json device_rules.json
```

The example MAC addresses are fictitious. Replace them with your station MACs
and review supported bands, preferred band, weights, thresholds and cooldowns.
Per-device JSON settings can override the global defaults. The examples retain
the source experiment's differing profiles; they are not a claim that every
client has the same switch threshold or cooldown.

## 3. Initialize and collect measurements

```bash
python -m wifi_steering.cli init-db
python -m wifi_steering.cli config
python -m wifi_steering.cli collect --once
python -m wifi_steering.cli collect --interval 5 --duration 60 --tag baseline
```

`config` prints the effective local configuration. `collect` contacts the AP
to read its current measurements. The default database is `rssi_lb.sqlite3`.
Do not run multiple collectors against the same experiment unless intentional.

## 4. Start the dashboard

Terminal 1, with the Python virtual environment active:

```bash
python -m wifi_steering.api
```

Terminal 2:

```bash
cd frontend
npm ci
npm run dev
```

Open **http://localhost:3000**. The API listens on **127.0.0.1:3001** by
default; the Vite development server proxies `/api` to that API. Browser API
requests use this same origin unless `frontend/.env` specifies `VITE_API_URL`.
Changing the backend port also requires updating the Vite proxy target.

For a separately served frontend, copy `frontend/.env.example` to
`frontend/.env` and set `VITE_API_URL` to the API origin without `/api`.
Configure permitted CORS origins in the backend for that deployment.
`npm run preview` previews a static build; it does not inherit the dev API proxy.

The API has no user-authentication layer and includes control endpoints. The
provided defaults are for local laboratory use. A public deployment requires
an authenticated access layer and appropriate network access controls.

Some template routes (such as team, calendar, contacts and geography) are
retained from the dashboard template and contain demo data. They are not AP
telemetry. The main experimental views are Steering, Configuration, RSSI,
Throughput, Retransmissions and Scores.

## 5. Inspect decisions, then apply steering

Observation / dry-run:

```bash
python -m wifi_steering.cli run --duration 60 --interval 5 --tag dry-run
```

To enable real actions, explicitly set `BPI_ALLOW_CHANGES=true` in `.env`,
restart an already running API, then run:

```bash
python -m wifi_steering.cli run --duration 180 --interval 5 --apply --tag steering
```

Both `--apply` and `BPI_ALLOW_CHANGES=true` are required for CLI application.
The dashboard's Start action also requires `BPI_ALLOW_CHANGES=true` and starts
the CLI with `--apply`. Do not run a second CLI steering loop while the API
already manages one. Dry-run still reads the AP and writes local diagnostics.

The controller enforces a minimum per-station cooldown of 60 seconds in its
decision path; configured rules can request a longer interval (the example
environment requests 180 seconds). Verify actual
request and association timestamps when reporting experiment transitions.

## API overview

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Local service status |
| GET | `/api/devices` | Discovered devices |
| GET | `/api/rssi` | RSSI history |
| GET | `/api/throughput` | Throughput history |
| GET | `/api/retransmissions` | Retry history |
| GET | `/api/station-metrics` | Stored station metrics from the configured database |
| GET | `/api/device-rules` | Per-device rule collection |
| GET / PUT / DELETE | `/api/device-rules/<mac>` | Read, update or remove one device rule |
| GET | `/api/steering` | Current steering state and diagnostics |
| POST | `/api/steering/start` | Start the managed steering process |
| POST | `/api/steering/stop` | Stop the managed steering process |
| POST | `/api/steering/restart` | Restart the managed steering process |
| GET | `/api/steering/logs` | Recent process logs |

Use the dashboard's configuration form for the supported rule payload. RSSI
and retry-history endpoints support optional filters such as `mac`, `band`
and `interface`. Some API histories are maintained in memory and/or sampled
when requested: keep the relevant monitoring views polling during recording.

## Export and reproduce experiments

```bash
python -m wifi_steering.cli export-csv --output exports/radios.csv
python -m wifi_steering.cli export-csv --interface phy0.1-ap0 --output exports/5ghz.csv
```

The dashboard also provides spreadsheet exports in relevant monitoring views.
Runtime databases, rules, SSH credentials and measurement exports are excluded
from this source release. Record the actual `.env` settings, device rules,
AP firmware, channels, bandwidths, traffic-generator settings and experiment
timestamps alongside your measurements. The example thresholds do not prove
that an earlier recording used the same values.

The original `sync-sessions` command remains available, but samples current
associations rather than reconstructing historical session start/end times.

## Metric limitations

- RSSI is read in dBm. A better RSSI does not by itself establish throughput
  compliance or energy savings.
- Throughput is derived from counters and elapsed time; it is not the radio's
  advertised PHY rate. Missing/inactive intervals and interface changes matter.
- Retry ratios may exceed 100% because multiple retries may be recorded for
  one transmitted packet. They are not packet-loss probabilities.
- The SSH client's fallback `total_airtime=0` is accompanied by
  `airtime_available=false`. This is **not a measured zero utilization**.
  Latency/loss and candidate-band values may be unavailable or estimated in
  existing scoring paths. Inspect diagnostics before presenting them as direct
  measurements of every band.
- Controller scores and history gaps are not a substitute for an AP action log
  confirming that a client accepted a steering request.
- Energy consumption is not measured by this implementation.

## Offline verification

```bash
python -m compileall -q wifi_steering
python -m unittest discover -s tests -v
cd frontend
npm run build
```

The tests cover schema initialization, rule-file creation, client dry-run and
CLI/API application gating without SSH access. Hardware collection, BSS-TM
acceptance and full live dashboard operation must be verified on your testbed.
See [preparation notes](docs/PREPARATION_NOTES.md) for verification of this release.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing `BPI_SSH_HOST` / no configured radios | Copy and edit the root `.env`; use the `AP1_RADIO_*` mappings |
| SSH host-key or authentication error | Verify the fingerprint and key manually with the same host, user and port |
| Empty clients or incorrect bands | Check `iw dev`, the interface convention and actual radio/UCI mapping |
| Start fails with changes disabled | Set `BPI_ALLOW_CHANGES=true` only when applying actions is intended, then restart the API |
| Scores do not match the paper's configuration | Inspect per-device JSON rules and effective environment settings |
| Graph request fails | Start the API and check Vite proxy / `VITE_API_URL` |
| `hostapd_cli` lacks BSS-TM support | Inspect your installed wpad/hostapd build before changing packages |

## Publication and licensing

The dashboard template's MIT license is preserved in `frontend/LICENSE`.
See [third-party notices](THIRD_PARTY_NOTICES.md) for attribution and branding.
No license was supplied for the original backend; the owner must choose one
before granting redistribution rights for the complete project.

The archive is prepared for a new GitHub repository. It contains no original
Git history, dependency environments, measurement databases or live `.env`.
Create a repository, then run from this folder, replacing the remote URL:

```bash
git init
git add .
git commit -m "Prepare OpenWrt Wi-Fi steering research prototype"
git branch -M main
git remote add origin https://github.com/YOUR_ACCOUNT/YOUR_REPOSITORY.git
git push -u origin main
```
# A-Multi-Metric-Framework-to-Dynamic-Tri-Band-Steering-in-Wi-Fi-6E-7-Networks

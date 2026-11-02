# Configuration reference

The root `.env.example` documents the intended local setup. Copy it to `.env`.
Existing process environment variables take precedence over values loaded from
`.env`. Restart the API after changing its environment configuration.

## Runtime files

| Variable | Purpose |
| --- | --- |
| `OPENWRT_DB_PATH` | SQLite telemetry/history database shared by CLI and station-metrics API |
| `OPENWRT_DEVICE_RULES_PATH` | Controller's per-device JSON file |
| `DEVICE_RULES_FILE` | API's per-device JSON file; set to the same path |
| `STEERING_STATE_FILE` | Shared latest controller diagnostics |
| `BPI_ALLOW_CHANGES` | Explicit application gate; defaults to false |
| `STEERING_DURATION` | Managed dashboard steering duration, seconds |
| `STEERING_INTERVAL` | Managed dashboard loop interval, seconds |
| `API_HOST`, `API_PORT` | Local Flask bind address and port |

Run commands from the repository root when using relative paths. Absolute
paths are also accepted. Do not share one state file among independent API
and controller instances unless their lifecycle is coordinated.

## Device rules

The file maps a station MAC to a rule object. The included example MACs are
locally administered fictitious addresses. Its profiles are adapted from the
provided JSON and preserve differing eligibility, score weights and cooldowns.
The experiment's actual MAC addresses and runtime state have been omitted.

| Field | Meaning |
| --- | --- |
| `device_type` | Human/device classification used by the existing controller |
| `priority` | Per-device priority |
| `bands` | Candidate band eligibility, keyed by `2G`, `5G`, `6G` |
| `preferred_band` | Preferred candidate band |
| `weights` | Relative weights for clients, RSSI, airtime, throughput, TX power |
| `thresholds.<band>.min_rssi` | Per-band minimum RSSI in dBm |
| `min_throughput_mbps` | Device throughput requirement |
| `max_airtime_percent` | Airtime-utilization requirement |
| `switch_threshold` | Required score improvement in existing decision paths |
| `cooldown` | Requested per-device interval between switches, seconds |

Environment defaults, `device_rules.py` defaults and API defaults are not
identical in the supplied implementation. Explicit JSON rules avoid relying
on an assumed common default. The preparation keeps those decision defaults
unchanged; `.env.example` sets an explicit baseline for new runs.

The controller's actual cooldown floor is `max(60.0, configured_cooldown)`.
An original comment saying 180 seconds was inaccurate and has been corrected.
The source example profiles can request 360 seconds. These differences matter
when reproducing or describing a particular recording.

## Metrics and interpretation

The primary SSH client's `airtime_available=false` means utilization was not
measured there. A fallback numeric zero must not be reported as real zero
occupancy. Latency and loss are not directly obtained from its `iw` snapshot.
Candidate scores may depend on estimates and fallbacks in existing code.

Historical experiment charts/Excel and the paper's plotting scripts are not
included in this repository; they were not present as source deliverables in
the uploaded project ZIP. Regenerate measurements and exports on your own AP.

Never infer that a configured rule was satisfied solely because an API returned
a score. Compare accepted steering actions, band observations, and measured
performance in a consistent time window.

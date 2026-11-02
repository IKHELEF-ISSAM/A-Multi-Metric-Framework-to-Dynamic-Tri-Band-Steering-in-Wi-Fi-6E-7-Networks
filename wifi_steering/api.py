import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Flask, jsonify, request
from flask_cors import CORS

from .client import OpenWrtClient
from .config import load_config
from .controller import normalize_snapshot


# ============================================================
# Flask
# ============================================================

app = Flask(__name__)
CORS(app, origins=["http://localhost:3000", "http://127.0.0.1:3000"])


# ============================================================
# Direct OpenWrt configuration
# ============================================================

config = load_config()

client = OpenWrtClient(config)

ap = config.ap


# ============================================================
# Configuration SSH BPI-R4
# ============================================================

BPI_SSH_HOST = os.getenv(
    "BPI_SSH_HOST",
    "192.168.1.10",
)

BPI_SSH_USER = os.getenv(
    "BPI_SSH_USER",
    "root",
)

BPI_SSH_PORT = os.getenv(
    "BPI_SSH_PORT",
    "22",
)

BPI_SSH_KEY = os.getenv(
    "BPI_SSH_KEY",
    "",
)


# ============================================================
# Steering configuration
# ============================================================

STEERING_STATE_FILE = Path(
    os.getenv(
        "STEERING_STATE_FILE",
        "./steering_state.json",
    )
)

STEERING_DURATION = int(
    os.getenv(
        "STEERING_DURATION",
        "600",
    )
)

STEERING_INTERVAL = os.getenv(
    "STEERING_INTERVAL",
    "",
)

STEERING_PROCESS: Optional[subprocess.Popen] = None

STEERING_LOG_LINES: List[str] = []

STEERING_LOCK = threading.RLock()

STEERING_LOG_MAX_LINES = 500

# ============================================================
# GET /api/retransmissions
# ========================
@app.route("/api/retransmissions", methods=["GET"])
def get_retransmissions():

    try:

        history = collect_retry_measurements()

        mac_filter = request.args.get("mac")
        band_filter = request.args.get("band")
        interface_filter = request.args.get("interface")

        if mac_filter:
            mac_filter = normalize_mac(mac_filter)
            history = [
                item for item in history
                if item["mac"] == mac_filter
            ]

        if band_filter:
            history = [
                item for item in history
                if item["band"].upper() == band_filter.upper()
            ]

        if interface_filter:
            history = [
                item for item in history
                if item["interface"] == interface_filter
            ]

        return jsonify({
            "count": len(history),
            "interval_seconds": RETRY_POLL_INTERVAL,
            "history_duration_seconds": RETRY_HISTORY_DURATION,
            "measurements": history,
        })

    except Exception as exc:

        app.logger.exception("Error collecting retransmissions")

        return jsonify({
            "error": str(exc),
            "measurements": [],
        }), 500
# ============================================================
# Device rules
# ============================================================

RULES_FILE = Path(
    os.getenv(
        "DEVICE_RULES_FILE",
        str(config.device_rules_path),
    )
)


DEFAULT_RULE = {
    "device_type": "Unknown",
    "priority": "medium",
    "bands": {
        "2G": True,
        "5G": True,
        "6G": True,
    },
    "preferred_band": "5G",
    "weights": {
        "clients": 0.10,
        "rssi": 0.30,
        "airtime": 0.25,
        "throughput": 0.25,
        "txpower": 0.10,
    },
    "thresholds": {
        "2G": {
            "min_rssi": -75,
        },
        "5G": {
            "min_rssi": -70,
        },
        "6G": {
            "min_rssi": -65,
        },
    },
    "min_throughput_mbps": 5,
    "max_airtime_percent": 80,
    "switch_threshold": 1,
    "cooldown": 180,
}


# ============================================================
# Utilities
# ============================================================

def normalize_mac(mac: Any) -> str:

    if not mac:
        return ""

    return (
        str(mac)
        .strip()
        .lower()
        .replace("-", ":")
    )


def safe_int(
    value: Any,
    default: int = 0,
) -> int:

    try:
        return int(float(value))

    except (TypeError, ValueError):
        return default


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:

    try:
        return float(value)

    except (TypeError, ValueError):
        return default


def deep_clone(data: Any) -> Any:

    return json.loads(
        json.dumps(data)
    )




@app.route("/api/throughput", methods=["GET"])
def get_throughput_history():
    stations = get_wifi_stations()
    history = record_throughput_measurements(stations)

    return jsonify({
        "count": len(history),
        "history_duration_seconds": THROUGHPUT_HISTORY_DURATION,
        "measurements": history,
    })
# ============================================================
# Steering process helpers
# ============================================================

def get_steering_process() -> Optional[subprocess.Popen]:
    """
    Return the current steering process.

    If the process has already exited, clear the reference.
    """

    global STEERING_PROCESS

    with STEERING_LOCK:

        if STEERING_PROCESS is None:
            return None

        if STEERING_PROCESS.poll() is not None:

            STEERING_PROCESS = None

            return None

        return STEERING_PROCESS


def append_steering_log(
    line: str,
) -> None:

    if not line:
        return

    with STEERING_LOCK:

        STEERING_LOG_LINES.append(
            line.rstrip()
        )

        if len(
            STEERING_LOG_LINES
        ) > STEERING_LOG_MAX_LINES:

            del STEERING_LOG_LINES[
                :-STEERING_LOG_MAX_LINES
            ]


def steering_process_reader(
    process: subprocess.Popen,
) -> None:
    """
    Read stdout from the steering process in the background.

    This prevents the child process from blocking on a full
    stdout pipe.
    """

    try:

        if process.stdout is None:
            return

        for line in process.stdout:

            line = line.rstrip()

            if line:

                print(
                    "[STEERING]",
                    line,
                    flush=True,
                )

                append_steering_log(
                    line
                )

    except Exception as exc:

        append_steering_log(
            f"[API] Steering log reader error: {exc}"
        )

    finally:

        return_code = process.poll()

        append_steering_log(
            "[API] Steering process exited "
            f"with code {return_code}"
        )


def write_api_steering_state(
    status: str,
    message: str = "",
) -> Dict[str, Any]:
    """
    Write a small API-level state only when necessary.

    The CLI normally owns steering_state.json and writes the
    detailed device diagnostics. We avoid overwriting that
    detailed state while the steering engine is running.
    """

    existing: Dict[str, Any] = {}

    try:

        if STEERING_STATE_FILE.exists():

            with STEERING_STATE_FILE.open(
                "r",
                encoding="utf-8",
            ) as file:

                loaded = json.load(file)

                if isinstance(
                    loaded,
                    dict,
                ):
                    existing = loaded

    except Exception:
        existing = {}

    existing.setdefault(
        "timestamp",
        time.time(),
    )

    existing["api_status"] = status

    if message:
        existing["api_message"] = message

    try:

        STEERING_STATE_FILE.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_file = (
            STEERING_STATE_FILE.with_suffix(
                ".api.tmp"
            )
        )

        with temporary_file.open(
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                existing,
                file,
                indent=2,
                ensure_ascii=False,
            )

        temporary_file.replace(
            STEERING_STATE_FILE
        )

    except Exception as exc:

        print(
            "[STEERING STATE ERROR]",
            repr(exc),
        )

    return existing


def build_steering_response(
    state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:

    process = get_steering_process()

    running = (
        process is not None
    )

    pid = (
        process.pid
        if process is not None
        else None
    )

    if state is None:

        state = {}

        try:

            if STEERING_STATE_FILE.exists():

                with STEERING_STATE_FILE.open(
                    "r",
                    encoding="utf-8",
                ) as file:

                    loaded = json.load(
                        file
                    )

                    if isinstance(
                        loaded,
                        dict,
                    ):
                        state = loaded

        except Exception:
            state = {}

    response = dict(state)

    response["engine"] = {
        "running": running,
        "pid": pid,
        "duration": STEERING_DURATION,
        "interval": STEERING_INTERVAL,
        "command": (
            "python3 -m wifi_steering.cli "
            f"run --duration {STEERING_DURATION} --apply"
        ),
    }

    if running:

        response["status"] = (
            response.get(
                "status"
            )
            or "running"
        )

    return response


def start_steering_process() -> Dict[str, Any]:

    global STEERING_PROCESS

    if not config.bpi_allow_changes:
        raise RuntimeError("Set BPI_ALLOW_CHANGES=true to enable steering actions.")

    with STEERING_LOCK:

        if (
            STEERING_PROCESS is not None
            and STEERING_PROCESS.poll() is None
        ):

            return build_steering_response()

        # ----------------------------------------------------
        # Clear previous API logs
        # ----------------------------------------------------

        STEERING_LOG_LINES.clear()

        # ----------------------------------------------------
        # Build command
        #
        # This is intentionally the same command requested:
        #
        # python3 -m wifi_steering.cli run
        #     --duration 60
        #     --apply
        # ----------------------------------------------------

        command = [
            sys.executable,
            "-m",
            "wifi_steering.cli",
            "run",
            "--duration",
            str(STEERING_DURATION),
            "--apply",
        ]

        # Optional interval from environment.
        if STEERING_INTERVAL:

            command.extend([
                "--interval",
                str(STEERING_INTERVAL),
            ])

        print(
            "[STEERING API] Starting:",
            " ".join(command),
            flush=True,
        )

        append_steering_log(
            "[API] Starting steering: "
            + " ".join(command)
        )

        try:

            STEERING_PROCESS = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=os.getcwd(),
                start_new_session=True,
            )

        except Exception as exc:

            STEERING_PROCESS = None

            append_steering_log(
                f"[API] Failed to start steering: {exc}"
            )

            return {
                "success": False,
                "error": str(exc),
                "engine": {
                    "running": False,
                    "pid": None,
                },
            }

        process = STEERING_PROCESS

        # ----------------------------------------------------
        # Read stdout asynchronously.
        # ----------------------------------------------------

        thread = threading.Thread(
            target=steering_process_reader,
            args=(process,),
            daemon=True,
        )

        thread.start()

        write_api_steering_state(
            "starting",
            "Steering process started.",
        )

        return build_steering_response()


def stop_steering_process() -> Dict[str, Any]:

    global STEERING_PROCESS

    with STEERING_LOCK:

        process = STEERING_PROCESS

        if process is None:

            return build_steering_response()

        if process.poll() is not None:

            STEERING_PROCESS = None

            return build_steering_response()

        pid = process.pid

        print(
            "[STEERING API] Stopping PID:",
            pid,
            flush=True,
        )

        append_steering_log(
            f"[API] Stopping steering process PID={pid}"
        )

        try:

            # Because Popen uses start_new_session=True,
            # terminate the complete process group.
            os.killpg(
                os.getpgid(pid),
                signal.SIGTERM,
            )

        except ProcessLookupError:
            pass

        except Exception as exc:

            print(
                "[STEERING API] SIGTERM error:",
                repr(exc),
            )

            append_steering_log(
                f"[API] SIGTERM error: {exc}"
            )

        # ----------------------------------------------------
        # Give the process a short grace period.
        # ----------------------------------------------------

        try:

            process.wait(
                timeout=5
            )

        except subprocess.TimeoutExpired:

            print(
                "[STEERING API] Process did not stop; "
                "sending SIGKILL.",
                flush=True,
            )

            append_steering_log(
                "[API] Process did not stop; sending SIGKILL."
            )

            try:

                os.killpg(
                    os.getpgid(pid),
                    signal.SIGKILL,
                )

            except Exception:
                pass

            try:
                process.wait(
                    timeout=3
                )
            except Exception:
                pass

        STEERING_PROCESS = None

        write_api_steering_state(
            "stopped",
            "Steering process stopped.",
        )

        return build_steering_response()


# ============================================================
# Device rules storage
# ============================================================

def load_device_rules() -> Dict[str, Any]:

    if not RULES_FILE.exists():
        return {}

    try:

        with RULES_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:

            data = json.load(
                file
            )

        if not isinstance(
            data,
            dict,
        ):
            return {}

        return data

    except Exception as exc:

        print(
            "[RULES ERROR] Cannot load rules:",
            repr(exc),
        )

        return {}


def save_device_rules(
    rules: Dict[str, Any],
) -> None:

    RULES_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_file = RULES_FILE.with_suffix(
        ".tmp"
    )

    with temporary_file.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            rules,
            file,
            indent=2,
            ensure_ascii=False,
        )

    temporary_file.replace(
        RULES_FILE
    )


def merge_rule(
    rule: Optional[Dict[str, Any]],
) -> Dict[str, Any]:

    result = deep_clone(
        DEFAULT_RULE
    )

    if not isinstance(
        rule,
        dict,
    ):
        return result

    scalar_fields = [
        "device_type",
        "priority",
        "preferred_band",
        "min_throughput_mbps",
        "max_airtime_percent",
        "switch_threshold",
        "cooldown",
    ]

    for field in scalar_fields:

        if field in rule:
            result[field] = rule[field]

    if isinstance(
        rule.get("bands"),
        dict,
    ):

        result["bands"].update(
            rule["bands"]
        )

    if isinstance(
        rule.get("weights"),
        dict,
    ):

        result["weights"].update(
            rule["weights"]
        )

    if isinstance(
        rule.get("thresholds"),
        dict,
    ):

        for band in [
            "2G",
            "5G",
            "6G",
        ]:

            threshold = rule[
                "thresholds"
            ].get(band)

            if isinstance(
                threshold,
                dict,
            ):

                result["thresholds"][
                    band
                ].update(
                    threshold
                )

    return result


# ============================================================
# SSH
# ============================================================

def run_ssh(
    command: str,
    timeout: int = 5,
) -> str:

    ssh_command = [
        "ssh",
        "-p",
        str(BPI_SSH_PORT),
        "-o",
        "ConnectTimeout=3",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "BatchMode=yes",
    ]

    if BPI_SSH_KEY:

        ssh_command.extend([
            "-i",
            BPI_SSH_KEY,
        ])

    ssh_command.append(
        f"{BPI_SSH_USER}@{BPI_SSH_HOST}"
    )

    ssh_command.append(
        command
    )

    try:

        result = subprocess.run(
            ssh_command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:

            print(
                "[SSH ERROR]",
                f"command={command!r}",
                f"stderr={result.stderr.strip()!r}",
            )

            return ""

        return result.stdout.strip()

    except subprocess.TimeoutExpired:

        print(
            "[SSH TIMEOUT]",
            command,
        )

        return ""

    except Exception as exc:

        print(
            "[SSH ERROR]",
            repr(exc),
        )

        return ""


# ============================================================
# Wi-Fi band detection
# ============================================================

def detect_band(
    interface_name: str,
) -> str:

    if not interface_name:
        return "Unknown"

    name = str(
        interface_name
    ).lower()

    if (
        "2g" in name
        or "2.4" in name
    ):
        return "2G"

    if (
        "5g" in name
        or "5ghz" in name
    ):
        return "5G"

    if (
        "6g" in name
        or "6ghz" in name
    ):
        return "6G"

    if "phy0.0" in name:
        return "2G"

    if "phy0.1" in name:
        return "5G"

    if "phy0.2" in name:
        return "6G"

    if "phy0" in name:
        return "2G"

    if "phy1" in name:
        return "5G"

    if "phy2" in name:
        return "6G"

    return "Unknown"


# ============================================================
# Neighbor table
# ============================================================

def get_neighbor_table() -> Dict[str, Dict[str, str]]:

    neighbors: Dict[
        str,
        Dict[str, str],
    ] = {}

    for command in [
        "ip neigh",
        "ip -6 neigh",
    ]:

        output = run_ssh(
            command
        )

        if not output:
            continue

        for raw_line in output.splitlines():

            line = raw_line.strip()

            if not line:
                continue

            parts = line.split()

            if not parts:
                continue

            ip_address = parts[0]

            mac = ""

            if "lladdr" in parts:

                try:

                    index = parts.index(
                        "lladdr"
                    )

                    if index + 1 < len(parts):

                        mac = normalize_mac(
                            parts[index + 1]
                        )

                except ValueError:
                    pass

            if not mac:
                continue

            if mac not in neighbors:

                neighbors[mac] = {
                    "ipv4": "",
                    "ipv6": "",
                }

            if ":" in ip_address:

                if not re.match(
                    r"^[0-9a-fA-F:]+$",
                    ip_address,
                ):
                    neighbors[mac][
                        "ipv6"
                    ] = ip_address

            else:

                neighbors[mac][
                    "ipv4"
                ] = ip_address

    return neighbors


# ============================================================
# Discover Wi-Fi interfaces
# ============================================================

def get_wifi_interfaces() -> List[str]:

    output = run_ssh(
        "iw dev"
    )

    interfaces: List[str] = []

    if output:

        for raw_line in output.splitlines():

            line = raw_line.strip()

            if line.startswith(
                "Interface "
            ):

                name = line[
                    len("Interface "):
                ].strip()

                if (
                    name
                    and name not in interfaces
                ):

                    interfaces.append(
                        name
                    )

    if not interfaces:

        interfaces = [
            "phy0.0-ap0",
            "phy0.1-ap0",
            "phy0.2-ap0",
        ]

    return interfaces


# ============================================================
# Parse iw station dump
# ============================================================
def parse_station_dump(
    output: str,
    interface_name: str,
) -> Dict[str, Dict[str, Any]]:

    stations = {}
    current_mac = None

    for raw_line in output.splitlines():

        line = raw_line.strip()

        if not line:
            continue

        match = re.match(
            r"Station\s+([0-9a-fA-F:]{17})",
            line,
        )

        if match:
            current_mac = normalize_mac(match.group(1))

            stations[current_mac] = {
                "mac": current_mac,
                "interface": interface_name,
                "band": detect_band(interface_name),
                "connected": True,
                "rssi": None,
                "signal_avg": None,
                "rx_bitrate": None,
                "tx_bitrate": None,
                "rx_bytes": 0,
                "tx_bytes": 0,
                "rx_packets": 0,
                "tx_packets": 0,
                "tx_retries": 0,
                "tx_failed": 0,
                "tx_duration": 0,
            }

            continue

        if not current_mac:
            continue

        station = stations[current_mac]

        patterns = {
            "rssi": (r"signal:\s*(-?\d+)", int),
            "signal_avg": (r"signal avg:\s*(-?\d+)", int),
            "rx_bytes": (r"rx bytes:\s*(\d+)", int),
            "tx_bytes": (r"tx bytes:\s*(\d+)", int),
            "rx_packets": (r"rx packets:\s*(\d+)", int),
            "tx_packets": (r"tx packets:\s*(\d+)", int),
            "tx_retries": (r"tx retries:\s*(\d+)", int),
            "tx_failed": (r"tx failed:\s*(\d+)", int),
            "tx_duration": (r"tx duration:\s*(\d+)", int),
            "rx_bitrate": (
                r"rx bitrate:\s*([0-9.]+)\s*MBit/s",
                lambda x: float(x) * 1_000_000,
            ),
            "tx_bitrate": (
                r"tx bitrate:\s*([0-9.]+)\s*MBit/s",
                lambda x: float(x) * 1_000_000,
            ),
        }

        matched = False

        for field, (pattern, converter) in patterns.items():

            match = re.match(pattern, line)

            if match:
                station[field] = converter(match.group(1))
                matched = True
                break

        if matched:
            continue

        if line.startswith("associated:"):

            value = line.split(":", 1)[1].strip()

            station["connected"] = value.lower() in {
                "yes",
                "true",
                "1",
            }

    return stations
# ============================================================
# Wi-Fi stations
# ============================================================

def get_wifi_stations() -> Dict[
    str,
    Dict[str, Any],
]:

    interfaces = get_wifi_interfaces()

    print(
        "[WIFI] Interfaces:",
        interfaces,
    )

    stations: Dict[
        str,
        Dict[str, Any],
    ] = {}

    for interface_name in interfaces:

        output = run_ssh(
            (
                "iw dev "
                f"{interface_name} "
                "station dump"
            )
        )

        if not output:
            continue

        parsed = parse_station_dump(
            output,
            interface_name,
        )

        stations.update(
            parsed
        )

    print(
        "[WIFI] Stations:",
        len(stations),
    )

    return stations


# ============================================================
# THROUGHPUT monitoring configuration
# ============================================================



THROUGHPUT_HISTORY_DURATION = 10 * 60  # 10 minutes
THROUGHPUT_HISTORY = deque(maxlen=50000)

THROUGHPUT_PREVIOUS = {}
THROUGHPUT_LOCK = threading.Lock()


def record_throughput_measurements(stations):
    now = time.time()
    monotonic_now = time.monotonic()

    measurements = []

    with THROUGHPUT_LOCK:
        for station in stations.values():
            mac = normalize_mac(station.get("mac", ""))
            interface = str(station.get("interface", "") or "")

            if not mac or not interface:
                continue

            rx_bytes = max(0, safe_int(station.get("rx_bytes", 0)))
            tx_bytes = max(0, safe_int(station.get("tx_bytes", 0)))

            key = (mac, interface)
            previous = THROUGHPUT_PREVIOUS.get(key)

            # Première observation : on mémorise les compteurs.
            if previous is None:
                THROUGHPUT_PREVIOUS[key] = (
                    rx_bytes,
                    tx_bytes,
                    monotonic_now,
                )
                continue

            previous_rx, previous_tx, previous_time = previous

            elapsed = monotonic_now - previous_time

            # Actualiser la référence pour la prochaine mesure.
            THROUGHPUT_PREVIOUS[key] = (
                rx_bytes,
                tx_bytes,
                monotonic_now,
            )

            if elapsed <= 0:
                continue

            # Gérer les remises à zéro éventuelles des compteurs.
            delta_rx = max(0, rx_bytes - previous_rx)
            delta_tx = max(0, tx_bytes - previous_tx)

            # Débit total reçu + transmis, en Mbps.
            throughput_mbps = (
                (delta_rx + delta_tx) * 8
                / elapsed
                / 1_000_000
            )

            measurements.append({
                "timestamp": now,
                "datetime": time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ",
                    time.gmtime(now),
                ),
                "mac": mac,
                "interface": interface,
                "band": station.get("band", "Unknown"),
                "throughput_mbps": round(throughput_mbps, 4),
            })

        # Ajouter les nouvelles mesures à l'historique.
        THROUGHPUT_HISTORY.extend(measurements)

        # Supprimer les mesures âgées de plus de 10 minutes.
        cutoff = now - THROUGHPUT_HISTORY_DURATION

        while (
            THROUGHPUT_HISTORY
            and THROUGHPUT_HISTORY[0]["timestamp"] < cutoff
        ):
            THROUGHPUT_HISTORY.popleft()

        return list(THROUGHPUT_HISTORY)


# ============================================================
# RSSI monitoring configuration
# ============================================================


RSSI_POLL_INTERVAL = 2  # Une collecte toutes les 2 secondes
RSSI_HISTORY_DURATION = 10 * 60  # Conserver 10 minutes
RSSI_HISTORY = deque(maxlen=50000)
RSSI_LOCK = threading.Lock()

# ============================================================
# Collect RSSI measurements
# ============================================================

def collect_rssi_measurements() -> List[Dict[str, Any]]:
    """
    Collect RSSI measurements from all Wi-Fi interfaces.

    Uses the existing SSH-based get_wifi_stations() function.
    """

    timestamp = time.time()

    stations = get_wifi_stations()

    measurements = []

    for mac, station in stations.items():

        rssi = station.get("rssi")

        if rssi is None:
            continue

        measurement = {
            "timestamp": timestamp,
            "datetime": datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc,
            ).isoformat(),
            "mac": normalize_mac(mac),
            "interface": station.get(
                "interface",
                "Unknown",
            ),
            "band": station.get(
                "band",
                "Unknown",
            ),
            "rssi": safe_int(rssi),
            "signal_avg": station.get(
                "signal_avg"
            ),
        }

        measurements.append(measurement)

    return measurements


# ============================================================
# GET /api/rssi
# ============================================================

@app.route(
    "/api/rssi",
    methods=["GET"],
)
def get_rssi():

    try:

        # Collect current measurements
        measurements = collect_rssi_measurements()

        now = time.time()
        cutoff = now - RSSI_HISTORY_DURATION

        with RSSI_LOCK:

            # Remove expired measurements
            while (
                RSSI_HISTORY
                and RSSI_HISTORY[0]["timestamp"] < cutoff
            ):
                RSSI_HISTORY.popleft()

            # Add the new measurements
            RSSI_HISTORY.extend(measurements)

            # Copy history while holding the lock
            history = list(RSSI_HISTORY)

        # Optional filters:
        # /api/rssi?mac=02:00:00:00:00:01
        # /api/rssi?band=5G
        # /api/rssi?interface=phy0.1-ap0

        mac_filter = request.args.get("mac")

        band_filter = request.args.get("band")

        interface_filter = request.args.get("interface")

        if mac_filter:

            mac_filter = normalize_mac(
                mac_filter
            )

            history = [
                item
                for item in history
                if item["mac"] == mac_filter
            ]

        if band_filter:

            history = [
                item
                for item in history
                if item["band"].upper()
                == band_filter.upper()
            ]

        if interface_filter:

            history = [
                item
                for item in history
                if item["interface"]
                == interface_filter
            ]

        return jsonify({
            "count": len(history),
            "interval_seconds": RSSI_POLL_INTERVAL,
            "history_duration_seconds": RSSI_HISTORY_DURATION,
            "measurements": history,
        })

    except Exception as exc:

        app.logger.exception(
            "Error collecting RSSI"
        )

        return jsonify({
            "error": str(exc),
            "measurements": [],
        }), 500
# ============================================================
# Device type detection
# ============================================================

def detect_device_type(
    hostname: str,
) -> Dict[str, Any]:

    if not hostname:

        return {
            "type": "Unknown",
            "confidence": 0.0,
        }

    name = (
        str(hostname)
        .lower()
        .strip()
    )

    if name in {
        "",
        "unknown",
        "unknown device",
        "localhost",
    }:

        return {
            "type": "Unknown",
            "confidence": 0.0,
        }

    smartphone_keywords = [
        "iphone",
        "android",
        "galaxy",
        "pixel",
        "xiaomi",
        "redmi",
        "oneplus",
        "huawei",
        "honor",
        "oppo",
        "realme",
    ]

    if any(
        keyword in name
        for keyword in smartphone_keywords
    ):

        return {
            "type": "Smartphone",
            "confidence": 0.90,
        }

    if "ipad" in name:

        return {
            "type": "Tablet",
            "confidence": 0.95,
        }

    if any(
        value in name
        for value in [
            "macbook",
            "imac",
            "mac-mini",
            "macmini",
        ]
    ):

        return {
            "type": "Laptop/Desktop",
            "confidence": 0.95,
        }

    if (
        name.startswith("desktop-")
        or name.startswith("laptop-")
        or "windows" in name
    ):

        return {
            "type": "PC",
            "confidence": 0.85,
        }

    if any(
        value in name
        for value in [
            "ubuntu",
            "debian",
            "linux",
        ]
    ):

        return {
            "type": "PC",
            "confidence": 0.80,
        }

    if any(
        value in name
        for value in [
            "chromecast",
            "google-tv",
            "android-tv",
            "firetv",
            "roku",
            "smart-tv",
        ]
    ):

        return {
            "type": "TV/Streaming",
            "confidence": 0.90,
        }

    if any(
        value in name
        for value in [
            "printer",
            "print",
            "hp-",
            "epson",
            "canon",
        ]
    ):

        return {
            "type": "Printer",
            "confidence": 0.80,
        }

    if any(
        value in name
        for value in [
            "esp32",
            "esp8266",
            "iot",
            "sensor",
            "tuya",
            "sonoff",
        ]
    ):

        return {
            "type": "IoT",
            "confidence": 0.90,
        }

    return {
        "type": "Unknown",
        "confidence": 0.0,
    }

# ============================================================
# RETRANSMISSION MONITORING
# ============================================================

RETRY_POLL_INTERVAL = 2
RETRY_HISTORY_DURATION = 10 * 60

RETRY_HISTORY = deque(maxlen=50000)
RETRY_PREVIOUS = {}

RETRY_LOCK = threading.Lock()

def collect_retry_measurements():

    timestamp = time.time()
    monotonic_now = time.monotonic()

    stations = get_wifi_stations()
    measurements = []

    with RETRY_LOCK:

        for mac, station in stations.items():

            mac = normalize_mac(mac)
            interface = station.get("interface", "")

            if not mac or not interface:
                continue

            current = {
                "packets": safe_int(station.get("tx_packets")),
                "retries": safe_int(station.get("tx_retries")),
                "failed": safe_int(station.get("tx_failed")),
                "duration": safe_int(station.get("tx_duration")),
            }

            print(
                f"[RETRY RAW] {mac} {interface} "
                f"packets={current['packets']} "
                f"retries={current['retries']} "
                f"failed={current['failed']}"
            )

            key = (mac, interface)
            previous = RETRY_PREVIOUS.get(key)

            # Première observation : mémoriser les compteurs.
            if previous is None:

                RETRY_PREVIOUS[key] = {
                    **current,
                    "time": monotonic_now,
                }

                print(f"[RETRY] Initial baseline: {mac}")
                continue

            elapsed = monotonic_now - previous["time"]

            if elapsed <= 0:
                continue

            delta_packets = current["packets"] - previous["packets"]
            delta_retries = current["retries"] - previous["retries"]
            delta_failed = current["failed"] - previous["failed"]
            delta_duration = current["duration"] - previous["duration"]

            # Toujours actualiser la référence.
            RETRY_PREVIOUS[key] = {
                **current,
                "time": monotonic_now,
            }

            # Compteurs réinitialisés ou station réinitialisée.
            if (
                delta_packets < 0
                or delta_retries < 0
                or delta_failed < 0
            ):
                print(f"[RETRY] Counter reset: {mac}")
                continue

            if delta_duration < 0:
                delta_duration = None

            # Retransmissions pour 100 paquets transmis.
            retry_rate = (
                delta_retries / delta_packets * 100
                if delta_packets > 0
                else None
            )

            measurement = {
                "timestamp": timestamp,
                "datetime": datetime.fromtimestamp(
                    timestamp,
                    tz=timezone.utc,
                ).isoformat(),
                "mac": mac,
                "interface": interface,
                "band": station.get("band", "Unknown"),
                "tx_packets": delta_packets,
                "tx_retries": delta_retries,
                "tx_failed": delta_failed,
                "tx_duration": delta_duration,
                "retry_rate": (
                    round(retry_rate, 3)
                    if retry_rate is not None
                    else None
                ),
                "elapsed": round(elapsed, 3),
            }

            measurements.append(measurement)

            print(
                f"[RETRY MEASURE] {mac} "
                f"packets={delta_packets} "
                f"retries={delta_retries} "
                f"rate={measurement['retry_rate']}"
            )

        RETRY_HISTORY.extend(measurements)

        cutoff = timestamp - RETRY_HISTORY_DURATION

        while (
            RETRY_HISTORY
            and RETRY_HISTORY[0]["timestamp"] < cutoff
        ):
            RETRY_HISTORY.popleft()

        return list(RETRY_HISTORY)

# ============================================================
# Generic client extraction
# ============================================================

def extract_clients_from_radio(
    radio: Dict[str, Any],
) -> List[Dict[str, Any]]:

    candidates = [
        radio.get("clients"),
        radio.get("stations"),
        radio.get("devices"),
        radio.get("associated_clients"),
        radio.get("associated_stations"),
    ]

    for clients in candidates:

        if isinstance(
            clients,
            list,
        ):
            return clients

    return []


# ============================================================
# Extract devices
# ============================================================

def extract_devices(
    snapshot: Dict[str, Any],
    neighbors: Dict[str, Dict[str, str]],
    wifi_stations: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:

    devices: Dict[
        str,
        Dict[str, Any],
    ] = {}

    if not isinstance(
        snapshot,
        dict,
    ):

        print(
            "[DEVICES] Invalid snapshot:",
            type(snapshot),
        )

        return []

    radios = snapshot.get(
        "radios",
        [],
    )

    if not isinstance(
        radios,
        list,
    ):

        radios = (
            snapshot.get(
                "wireless",
                [],
            )
            or snapshot.get(
                "interfaces",
                [],
            )
            or []
        )

    if not isinstance(
        radios,
        list,
    ):

        print(
            "[DEVICES] No radio list found"
        )

        return []

    print(
        "[DEVICES] Radio count:",
        len(radios),
    )

    for radio in radios:

        if not isinstance(
            radio,
            dict,
        ):
            continue

        interface_name = (
            radio.get(
                "interface_name"
            )
            or radio.get(
                "interface"
            )
            or radio.get(
                "ifname"
            )
            or radio.get(
                "name"
            )
            or ""
        )

        radio_band = (
            radio.get(
                "band"
            )
            or radio.get(
                "frequency_band"
            )
            or detect_band(
                interface_name
            )
        )

        clients = extract_clients_from_radio(
            radio
        )

        print(
            "[DEVICES] Radio:",
            interface_name,
            "band=",
            radio_band,
            "clients=",
            len(clients),
        )

        for raw_client in clients:

            if not isinstance(
                raw_client,
                dict,
            ):
                continue

            mac = normalize_mac(
                raw_client.get(
                    "mac"
                )
                or raw_client.get(
                    "address"
                )
                or raw_client.get(
                    "station"
                )
                or raw_client.get(
                    "station_mac"
                )
                or raw_client.get(
                    "client_mac"
                )
            )

            if not mac:
                continue

            hostname = (
                raw_client.get(
                    "hostname"
                )
                or raw_client.get(
                    "host_name"
                )
                or raw_client.get(
                    "device_name"
                )
                or raw_client.get(
                    "name"
                )
                or "Unknown device"
            )

            ip = (
                raw_client.get(
                    "ip"
                )
                or raw_client.get(
                    "ip_address"
                )
                or raw_client.get(
                    "ipAddress"
                )
                or ""
            )

            rssi = (
                raw_client.get(
                    "rssi"
                )
                if raw_client.get(
                    "rssi"
                ) is not None
                else raw_client.get(
                    "signal"
                )
            )

            band = (
                raw_client.get(
                    "band"
                )
                or radio_band
                or detect_band(
                    interface_name
                )
            )

            neighbor = neighbors.get(
                mac,
                {},
            )

            ipv4 = neighbor.get(
                "ipv4",
                "",
            )

            ipv6 = neighbor.get(
                "ipv6",
                "",
            )

            if not ip:
                ip = ipv4

            station = wifi_stations.get(
                mac,
                {},
            )

            if station:

                interface_name = (
                    station.get(
                        "interface"
                    )
                    or interface_name
                )

                if (
                    not band
                    or band == "Unknown"
                ):

                    band = (
                        station.get(
                            "band"
                        )
                        or band
                    )

                if station.get(
                    "rssi"
                ) is not None:

                    rssi = station[
                        "rssi"
                    ]

            type_info = detect_device_type(
                hostname
            )

            rx_rate = raw_client.get(
                "rx_bitrate"
            )

            tx_rate = raw_client.get(
                "tx_bitrate"
            )

            raw_rate = raw_client.get(
                "rate"
            )

            if isinstance(
                raw_rate,
                dict,
            ):

                if rx_rate is None:
                    rx_rate = raw_rate.get(
                        "rx"
                    )

                if tx_rate is None:
                    tx_rate = raw_rate.get(
                        "tx"
                    )

            if station:

                if station.get(
                    "rx_bitrate"
                ) is not None:

                    rx_rate = station[
                        "rx_bitrate"
                    ]

                if station.get(
                    "tx_bitrate"
                ) is not None:

                    tx_rate = station[
                        "tx_bitrate"
                    ]

            connected = raw_client.get(
                "connected"
            )

            if connected is None:

                connected = station.get(
                    "connected",
                    True,
                )

            device = {
                "mac": mac,
                "hostname": hostname,
                "ip": ip,
                "ipv4": ipv4,
                "ipv6": ipv6,
                "vendor": (
                    raw_client.get(
                        "vendor"
                    )
                    or "Unknown"
                ),
                "type": type_info[
                    "type"
                ],
                "type_confidence": type_info[
                    "confidence"
                ],
                "band": band or "Unknown",
                "interface": interface_name,
                "rssi": safe_int(
                    rssi,
                    0,
                ),
                "connected": bool(
                    connected
                ),
                "rate": {
                    "rx": safe_int(
                        rx_rate,
                        0,
                    ),
                    "tx": safe_int(
                        tx_rate,
                        0,
                    ),
                },
            }

            devices[mac] = device

    # --------------------------------------------------------
    # Fallback to direct iw station data.
    # --------------------------------------------------------

    for mac, station in wifi_stations.items():

        if mac in devices:
            continue

        hostname = "Unknown device"

        type_info = detect_device_type(
            hostname
        )

        device = {
            "mac": mac,
            "hostname": hostname,
            "ip": neighbors.get(
                mac,
                {},
            ).get(
                "ipv4",
                "",
            ),
            "ipv4": neighbors.get(
                mac,
                {},
            ).get(
                "ipv4",
                "",
            ),
            "ipv6": neighbors.get(
                mac,
                {},
            ).get(
                "ipv6",
                "",
            ),
            "vendor": "Unknown",
            "type": type_info[
                "type"
            ],
            "type_confidence": type_info[
                "confidence"
            ],
            "band": (
                station.get(
                    "band"
                )
                or detect_band(
                    station.get(
                        "interface",
                        "",
                    )
                )
            ),
            "interface": station.get(
                "interface",
                "",
            ),
            "rssi": safe_int(
                station.get(
                    "rssi"
                ),
                0,
            ),
            "connected": bool(
                station.get(
                    "connected",
                    True,
                )
            ),
            "rate": {
                "rx": safe_int(
                    station.get(
                        "rx_bitrate"
                    ),
                    0,
                ),
                "tx": safe_int(
                    station.get(
                        "tx_bitrate"
                    ),
                    0,
                ),
            },
        }

        devices[mac] = device

    result = list(
        devices.values()
    )

    print(
        "[DEVICES] Final device count:",
        len(result),
    )

    return result


# ============================================================
# GET /api/devices
# ============================================================

@app.route(
    "/api/devices",
    methods=["GET"],
)
def get_devices():

    try:

        print(
            "[API] Fetching OpenWrt snapshot..."
        )

        raw_snapshot = (
            client.get_monitoring_snapshot(
                ap
            )
        )

        print(
            "[API] Raw snapshot type:",
            type(raw_snapshot),
        )

        normalized = normalize_snapshot(
            raw_snapshot,
            config,
            ap,
        )

        print(
            "[API] Normalized snapshot type:",
            type(normalized),
        )

        if isinstance(
            normalized,
            dict,
        ):

            print(
                "[API] Snapshot keys:",
                list(
                    normalized.keys()
                ),
            )

        neighbors = (
            get_neighbor_table()
        )

        wifi_stations = (
            get_wifi_stations()
        )

        devices = extract_devices(
            normalized,
            neighbors,
            wifi_stations,
        )

        return jsonify({
            "devices": devices,
            "count": len(devices),
        })

    except Exception as exc:

        print(
            "[API ERROR] /api/devices:",
            repr(exc),
        )

        return jsonify({
            "error": str(exc),
            "devices": [],
            "count": 0,
        }), 500


# ============================================================
# POST /api/devices
# ============================================================

@app.route(
    "/api/devices",
    methods=["POST"],
)
def save_devices():

    try:

        data = request.get_json(
            silent=True
        )

        if data is None:

            return jsonify({
                "success": False,
                "error": "Invalid JSON",
            }), 400

        return jsonify({
            "success": True,
            "devices": data,
        })

    except Exception as exc:

        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500


# ============================================================
# GET /api/device-rules
# ============================================================

@app.route(
    "/api/device-rules",
    methods=["GET"],
)
def get_device_rules():

    try:

        rules = load_device_rules()

        return jsonify({
            "rules": rules,
            "count": len(rules),
        })

    except Exception as exc:

        print(
            "[API ERROR] /api/device-rules:",
            repr(exc),
        )

        return jsonify({
            "error": str(exc),
            "rules": {},
            "count": 0,
        }), 500


# ============================================================
# GET /api/device-rules/<mac>
# ============================================================

@app.route(
    "/api/device-rules/<path:mac>",
    methods=["GET"],
)
def get_device_rule(mac):

    try:

        mac = normalize_mac(
            mac
        )

        if not mac:

            return jsonify({
                "error": "Invalid MAC address",
            }), 400

        rules = load_device_rules()

        rule = rules.get(
            mac
        )

        if rule is None:

            return jsonify({
                "mac": mac,
                "exists": False,
                "rule": merge_rule(
                    None
                ),
            })

        return jsonify({
            "mac": mac,
            "exists": True,
            "rule": merge_rule(
                rule
            ),
        })

    except Exception as exc:

        print(
            "[API ERROR] GET device rule:",
            repr(exc),
        )

        return jsonify({
            "error": str(exc),
        }), 500


# ============================================================
# PUT /api/device-rules/<mac>
# ============================================================

@app.route(
    "/api/device-rules/<path:mac>",
    methods=["PUT"],
)
def update_device_rule(mac):

    try:

        mac = normalize_mac(
            mac
        )

        if not mac:

            return jsonify({
                "error": "Invalid MAC address",
            }), 400

        data = request.get_json(
            silent=True
        )

        if not isinstance(
            data,
            dict,
        ):

            return jsonify({
                "error": (
                    "Request body must be "
                    "a JSON object"
                ),
            }), 400

        rule = merge_rule(
            data
        )

        enabled_bands = [
            band
            for band, enabled
            in rule["bands"].items()
            if bool(enabled)
        ]

        if not enabled_bands:

            return jsonify({
                "error": (
                    "At least one Wi-Fi "
                    "band must be enabled."
                ),
            }), 400

        if (
            rule["preferred_band"]
            not in enabled_bands
        ):

            return jsonify({
                "error": (
                    "Preferred band must "
                    "be enabled."
                ),
            }), 400

        weights = rule.get(
            "weights",
            {},
        )

        total_weight = sum(
            safe_float(
                value,
                0,
            )
            for value in weights.values()
        )

        if abs(
            total_weight - 1.0
        ) > 0.001:

            return jsonify({
                "error": (
                    "Weights must total 100%. "
                    f"Current total: "
                    f"{total_weight * 100:.1f}%."
                ),
            }), 400

        rule[
            "min_throughput_mbps"
        ] = safe_float(
            rule.get(
                "min_throughput_mbps"
            ),
            5,
        )

        rule[
            "max_airtime_percent"
        ] = safe_float(
            rule.get(
                "max_airtime_percent"
            ),
            80,
        )

        rule[
            "switch_threshold"
        ] = safe_float(
            rule.get(
                "switch_threshold"
            ),
            1,
        )

        rule[
            "cooldown"
        ] = safe_float(
            rule.get(
                "cooldown"
            ),
            180,
        )

        rules = load_device_rules()

        rules[mac] = rule

        save_device_rules(
            rules
        )

        print(
            "[RULES] Saved:",
            mac,
        )

        return jsonify({
            "success": True,
            "mac": mac,
            "rule": rule,
        })

    except Exception as exc:

        print(
            "[API ERROR] PUT device rule:",
            repr(exc),
        )

        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500


# ============================================================
# DELETE /api/device-rules/<mac>
# ============================================================

@app.route(
    "/api/device-rules/<path:mac>",
    methods=["DELETE"],
)
def delete_device_rule(mac):

    try:

        mac = normalize_mac(
            mac
        )

        if not mac:

            return jsonify({
                "error": "Invalid MAC address",
            }), 400

        rules = load_device_rules()

        existed = mac in rules

        rules.pop(
            mac,
            None,
        )

        save_device_rules(
            rules
        )

        return jsonify({
            "success": True,
            "mac": mac,
            "deleted": existed,
        })

    except Exception as exc:

        print(
            "[API ERROR] DELETE device rule:",
            repr(exc),
        )

        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500


# ============================================================
# GET /api/steering
# ============================================================

@app.route(
    "/api/steering",
    methods=["GET"],
)
def api_steering():

    try:

        state: Dict[str, Any] = {}

        if STEERING_STATE_FILE.exists():

            with STEERING_STATE_FILE.open(
                "r",
                encoding="utf-8",
            ) as file:

                loaded = json.load(
                    file
                )

                if isinstance(
                    loaded,
                    dict,
                ):
                    state = loaded

        if not state:

            state = {
                "timestamp": None,
                "status": "no_data",
                "devices": [],
                "message": (
                    "steering_state.json "
                    "not found"
                ),
            }

        return jsonify(
            build_steering_response(
                state
            )
        )

    except Exception as exc:

        print(
            "[API ERROR] /api/steering:",
            repr(exc),
        )

        return jsonify({
            "timestamp": None,
            "status": "error",
            "devices": [],
            "error": str(exc),
            "engine": {
                "running": (
                    get_steering_process()
                    is not None
                ),
            },
        }), 500


# ============================================================
# POST /api/steering/start
# ============================================================

@app.route(
    "/api/steering/start",
    methods=["POST"],
)
def api_steering_start():

    try:

        process = get_steering_process()

        if process is not None:

            return jsonify({
                "success": True,
                "already_running": True,
                "message": (
                    "Steering is already running."
                ),
                **build_steering_response(),
            })

        result = start_steering_process()

        if not result.get(
            "engine",
            {},
        ).get(
            "running",
            False,
        ):

            return jsonify(
                result
            ), 500

        return jsonify({
            "success": True,
            "message": (
                "Steering started successfully."
            ),
            **result,
        })

    except Exception as exc:

        print(
            "[API ERROR] /api/steering/start:",
            repr(exc),
        )

        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500

# ============================================================
# GET /api/station-metrics
# ============================================================

@app.route(
    "/api/station-metrics",
    methods=["GET"],
)
def get_station_metrics():

    """
    Retourne les métriques des stations
    enregistrées dans SQLite.

    Source :
        station_metrics

    Exemple de réponse :

    [
        {
            "timestamp": "2026-10-08T12:20:20+00:00",
            "station_mac": "02:00:00:00:00:01",
            "band": "6G",
            "rssi": -61.0,
            "clients": 1,
            "airtime": 0.0
        }
    ]
    """

    import sqlite3

    # --------------------------------------------------------
    # Localisation de la base SQLite
    # --------------------------------------------------------

    db_path = config.db_path

    try:

        # ----------------------------------------------------
        # Connexion SQLite
        # ----------------------------------------------------

        connection = sqlite3.connect(
            db_path
        )

        connection.row_factory = (
            sqlite3.Row
        )

        cursor = connection.cursor()

        # ----------------------------------------------------
        # Requête
        # ----------------------------------------------------

        cursor.execute(
            """
            SELECT
                timestamp,
                station_mac,
                band,
                rssi,
                clients,
                airtime
            FROM station_metrics
            ORDER BY timestamp ASC
            """
        )

        rows = cursor.fetchall()

        # ----------------------------------------------------
        # Conversion SQLite -> JSON
        # ----------------------------------------------------

        metrics = []

        for row in rows:

            metrics.append({
                "timestamp": row["timestamp"],
                "station_mac": row[
                    "station_mac"
                ],
                "band": row["band"],
                "rssi": row["rssi"],
                "clients": row["clients"],
                "airtime": row["airtime"],
            })

        connection.close()

        print(
            "[API] Station metrics:",
            len(metrics),
            "rows",
        )

        return jsonify(
            metrics
        )

    except Exception as exc:

        print(
            "[API ERROR] /api/station-metrics:",
            repr(exc),
        )

        return jsonify({
            "error": str(exc),
            "metrics": [],
        }), 500
# ============================================================
# POST /api/steering/stop
# ============================================================

@app.route(
    "/api/steering/stop",
    methods=["POST"],
)
def api_steering_stop():

    try:

        process = get_steering_process()

        if process is None:

            return jsonify({
                "success": True,
                "already_stopped": True,
                "message": (
                    "Steering is not running."
                ),
                **build_steering_response(),
            })

        result = stop_steering_process()

        return jsonify({
            "success": True,
            "message": (
                "Steering stopped successfully."
            ),
            **result,
        })

    except Exception as exc:

        print(
            "[API ERROR] /api/steering/stop:",
            repr(exc),
        )

        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500


# ============================================================
# POST /api/steering/restart
# ============================================================

@app.route(
    "/api/steering/restart",
    methods=["POST"],
)
def api_steering_restart():

    try:

        process = get_steering_process()

        if process is not None:

            stop_steering_process()

            time.sleep(
                0.5
            )

        result = start_steering_process()

        if not result.get(
            "engine",
            {},
        ).get(
            "running",
            False,
        ):

            return jsonify(
                result
            ), 500

        return jsonify({
            "success": True,
            "message": (
                "Steering restarted successfully."
            ),
            **result,
        })

    except Exception as exc:

        print(
            "[API ERROR] /api/steering/restart:",
            repr(exc),
        )

        return jsonify({
            "success": False,
            "error": str(exc),
        }), 500


# ============================================================
# GET /api/steering/logs
# ============================================================

@app.route(
    "/api/steering/logs",
    methods=["GET"],
)
def api_steering_logs():

    try:

        try:
            limit = int(
                request.args.get(
                    "limit",
                    "100",
                )
            )

        except ValueError:
            limit = 100

        limit = max(
            1,
            min(
                limit,
                STEERING_LOG_MAX_LINES,
            ),
        )

        with STEERING_LOCK:

            logs = list(
                STEERING_LOG_LINES[
                    -limit:
                ]
            )

        process = get_steering_process()

        return jsonify({
            "running": process is not None,
            "pid": (
                process.pid
                if process is not None
                else None
            ),
            "lines": logs,
            "count": len(logs),
        })

    except Exception as exc:

        return jsonify({
            "error": str(exc),
            "lines": [],
            "count": 0,
        }), 500


# ============================================================
# GET /api/health
# ============================================================

@app.route(
    "/api/health",
    methods=["GET"],
)
def health():

    process = get_steering_process()

    return jsonify({
        "status": "ok",
        "ap": getattr(
            ap,
            "name",
            "AP1",
        ),
        "device_id": getattr(
            ap,
            "device_id",
            "",
        ),
        "bpi_ssh_host": BPI_SSH_HOST,
        "rules_file": str(
            RULES_FILE.resolve()
        ),
        "steering": {
            "running": process is not None,
            "pid": (
                process.pid
                if process is not None
                else None
            ),
            "duration": STEERING_DURATION,
        },
    })


# ============================================================
# GET /api/debug/network
# ============================================================

@app.route(
    "/api/debug/network",
    methods=["GET"],
)
def debug_network():

    try:

        interfaces = (
            get_wifi_interfaces()
        )

        stations = (
            get_wifi_stations()
        )

        neighbors = (
            get_neighbor_table()
        )

        return jsonify({
            "ssh": {
                "host": BPI_SSH_HOST,
                "user": BPI_SSH_USER,
                "port": BPI_SSH_PORT,
            },
            "interfaces": interfaces,
            "stations": stations,
            "station_count": len(
                stations
            ),
            "neighbors": neighbors,
            "neighbor_count": len(
                neighbors
            ),
        })

    except Exception as exc:

        return jsonify({
            "error": str(exc),
        }), 500


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":

    app.run(
        host=os.getenv("API_HOST", "127.0.0.1"),
        port=int(os.getenv("API_PORT", "3001")),
        debug=False,
    )

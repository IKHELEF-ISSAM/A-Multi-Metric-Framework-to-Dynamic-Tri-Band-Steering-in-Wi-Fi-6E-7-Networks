"""
Command-line entry point for the OpenWrt BPI-R4
single-AP multi-radio / multi-metric station-placement optimizer.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .client import OpenWrtClient
from .config import AppConfig, load_config
from .controller import (
    ControlAction,
    MultiMetricSingleAPController,
    normalize_snapshot,
)
from .storage import Storage


# ============================================================================
# STEERING STATE
# ============================================================================

STEERING_STATE_FILE = Path(
    os.getenv(
        "STEERING_STATE_FILE",
        "./steering_state.json",
    )
)


def save_steering_state(
    controller: MultiMetricSingleAPController,
) -> None:
    """
    Persist the latest steering diagnostics.

    Flask reads this file through /api/steering.
    Atomic replacement prevents Flask from reading
    a partially written JSON file.
    """

    state = getattr(
        controller,
        "last_steering_state",
        None,
    )

    if not isinstance(state, dict):
        state = {
            "timestamp": time.time(),
            "status": "idle",
            "devices": [],
        }

    state.setdefault(
        "timestamp",
        time.time(),
    )

    state.setdefault(
        "status",
        "idle",
    )

    state.setdefault(
        "devices",
        [],
    )

    STEERING_STATE_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = None

    try:

        fd, temporary_path = tempfile.mkstemp(
            prefix=".steering_state_",
            suffix=".json",
            dir=str(
                STEERING_STATE_FILE.parent
            ),
        )

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as file:

            json.dump(
                state,
                file,
                indent=2,
                ensure_ascii=False,
            )

            file.flush()

            try:
                os.fsync(
                    file.fileno()
                )
            except OSError:
                pass

        os.replace(
            temporary_path,
            STEERING_STATE_FILE,
        )

        temporary_path = None

    except Exception:

        if temporary_path:

            try:
                os.unlink(
                    temporary_path
                )
            except OSError:
                pass

        raise


def write_steering_error(
    controller: MultiMetricSingleAPController,
    message: str,
) -> None:
    """
    Write a visible controller error to the dashboard state.
    """

    controller.last_steering_state = {
        "timestamp": time.time(),
        "status": "error",
        "devices": [],
        "message": message,
    }

    try:
        save_steering_state(
            controller
        )
    except Exception as exc:
        print(
            "[steering-state] "
            f"Unable to save error state: {exc}"
        )


# ============================================================================
# TIME
# ============================================================================


def utc_now() -> str:

    return (
        datetime.now(
            timezone.utc
        )
        .replace(
            microsecond=0
        )
        .isoformat()
    )


# ============================================================================
# FORMAT
# ============================================================================


def _format_optional(
    value: Any,
    digits: int = 1,
    suffix: str = "",
    width: int | None = None,
) -> str:

    if value is None:

        text = "NA"

    else:

        try:

            text = (
                f"{float(value):.{digits}f}"
                f"{suffix}"
            )

        except (
            TypeError,
            ValueError,
        ):

            text = "NA"

    if width is not None:

        return f"{text:>{width}}"

    return text


def _format_int(
    value: Any,
    width: int | None = None,
) -> str:

    if value is None:

        text = "NA"

    else:

        try:

            text = str(
                int(value)
            )

        except (
            TypeError,
            ValueError,
        ):

            text = "NA"

    if width is not None:

        return f"{text:>{width}}"

    return text


# ============================================================================
# COLLECTION
# ============================================================================


def collect_iteration(
    client: OpenWrtClient,
    storage: Storage,
    config: AppConfig,
    controller: (
        MultiMetricSingleAPController
        | None
    ) = None,
) -> dict[str, dict[str, Any]]:

    ap = config.ap

    raw_snapshot = (
        client.get_monitoring_snapshot(
            ap
        )
    )

    normalized = normalize_snapshot(
        raw_snapshot,
        config,
        ap,
    )

    if controller is not None:

        controller._prepare_snapshot(
            normalized
        )

    storage.insert_snapshot(
        timestamp=utc_now(),
        ap_id=normalized[
            "ap_id"
        ],
        ap_name=normalized[
            "ap_name"
        ],
        radios=normalized[
            "radios"
        ],
        raw_json=normalized[
            "raw"
        ],
    )

    for radio in normalized[
        "radios"
    ]:

        storage.insert_radio_metric(
            timestamp=utc_now(),
            radio=radio,
        )

    return {
        ap.name: normalized
    }


# ============================================================================
# SNAPSHOT DISPLAY
# ============================================================================


def print_snapshot(
    snapshots: dict[
        str,
        dict[str, Any],
    ],
) -> None:

    ts = datetime.now(
        timezone.utc
    ).strftime(
        "%H:%M:%S"
    )

    print()
    print(
        f"[{ts}] "
        "BPI-R4 multi-metric telemetry"
    )

    print(
        "-" * 145
    )

    found_radio = False

    for ap_name, snapshot in (
        snapshots.items()
    ):

        print()
        print(
            f"AP: {ap_name}"
        )

        print(
            " BAND | "
            "INTERFACE           | "
            "STA | "
            "RSSI      | "
            "TX        | "
            "AIRTIME   | "
            "THROUGHPUT       | "
            "LOSS      | "
            "LATENCY       | "
            "LOAD      | "
            "SCORE"
        )

        print(
            "-" * 145
        )

        radios = snapshot.get(
            "radios",
            [],
        )

        if not radios:

            print(
                "No configured wireless radios found."
            )

            continue

        for radio in radios:

            found_radio = True

            interface_name = getattr(
                radio,
                "interface_name",
                "",
            )

            band = getattr(
                radio,
                "band",
                "UNKNOWN",
            )

            client_count = getattr(
                radio,
                "client_count",
                None,
            )

            rssi = _format_optional(
                getattr(
                    radio,
                    "avg_signal",
                    None,
                ),
                digits=1,
            )

            txpower = _format_optional(
                getattr(
                    radio,
                    "tx_power",
                    None,
                ),
                digits=0,
                suffix=" dBm",
            )

            airtime = _format_int(
                getattr(
                    radio,
                    "total_airtime",
                    None,
                )
            )

            throughput = _format_optional(
                getattr(
                    radio,
                    "throughput_mbps",
                    0.0,
                ),
                digits=4,
                suffix=" Mbps",
            )

            packet_loss = _format_optional(
                getattr(
                    radio,
                    "packet_loss",
                    0.0,
                ),
                digits=2,
                suffix="%",
            )

            latency = _format_optional(
                getattr(
                    radio,
                    "latency_ms",
                    0.0,
                ),
                digits=1,
                suffix=" ms",
            )

            interface_load = _format_optional(
                getattr(
                    radio,
                    "interface_load",
                    0.0,
                ),
                digits=1,
            )

            score = _format_optional(
                getattr(
                    radio,
                    "score",
                    0.0,
                ),
                digits=3,
            )

            print(
                f"{band:>4} | "
                f"{interface_name:<19} | "
                f"{_format_int(client_count, 3)} | "
                f"{rssi:>9} | "
                f"{txpower:>9} | "
                f"{airtime:>9} | "
                f"{throughput:>16} | "
                f"{packet_loss:>9} | "
                f"{latency:>13} | "
                f"{interface_load:>9} | "
                f"{score}"
            )

    if not found_radio:

        print(
            "No radio telemetry available."
        )

    print(
        "-" * 145
    )


# ============================================================================
# SCORE DISPLAY
# ============================================================================


def print_scores(
    snapshots: dict[
        str,
        dict[str, Any],
    ],
) -> None:

    print()
    print(
        "[MULTI-METRIC RADIO SCORES]"
    )

    print(
        "-" * 90
    )

    for ap_name, snapshot in (
        snapshots.items()
    ):

        print(
            f"AP: {ap_name}"
        )

        radios = snapshot.get(
            "radios",
            [],
        )

        if not radios:

            print(
                "  No radios."
            )

            continue

        for radio in sorted(
            radios,
            key=lambda item: item.score,
            reverse=True,
        ):

            print(
                f"  {radio.band:<3} "
                f"{radio.interface_name:<20} "
                f"clients={radio.client_count:<3} "
                f"RSSI="
                f"{_format_optional(radio.avg_signal, 1):>7} "
                f"TP="
                f"{_format_optional(radio.throughput_mbps, 2):>9} "
                f"airtime="
                f"{radio.total_airtime:<8} "
                f"TX="
                f"{_format_optional(radio.tx_power, 0):>6} "
                f"score="
                f"{radio.score:.4f}"
            )

    print(
        "-" * 90
    )


# ============================================================================
# DECISION DISPLAY
# ============================================================================


def print_decision(
    action: ControlAction,
) -> None:

    print()
    print(
        "=" * 100
    )

    print(
        "[STATION PLACEMENT DECISION]"
    )

    print(
        "=" * 100
    )

    print(
        f"AP              : "
        f"{action.ap.name}"
    )

    print(
        f"Station         : "
        f"{action.station or 'unknown'}"
    )

    print(
        f"Source band     : "
        f"{action.source_band or action.band}"
    )

    print(
        f"Source interface: "
        f"{action.interface_name}"
    )

    print(
        f"Source score    : "
        f"{action.score_current:.2f}"
    )

    print(
        f"Target band     : "
        f"{action.target_band or 'unknown'}"
    )

    print(
        f"Target interface: "
        f"{action.target_interface or 'unknown'}"
    )

    print(
        f"Target BSSID    : "
        f"{action.target_bssid or 'unknown'}"
    )

    print(
        f"Target score    : "
        f"{action.score_target:.2f}"
    )

    print(
        f"Improvement     : "
        f"{action.improvement:.2f}"
    )

    print(
        f"Action          : "
        f"{action.action_type}"
    )

    print(
        f"Reason          : "
        f"{action.reason}"
    )

    print()
    print(
        "Command:"
    )

    print(
        action.command
    )

    print(
        "=" * 100
    )


# ============================================================================
# SSH AP1
# ============================================================================


def _ap1_ssh_target():
    cfg = load_config()
    return f"{cfg.bpi_ssh_user}@{cfg.bpi_ssh_host}"


def execute_ap1_ssh(
    command: str,
    timeout: float = 30.0,
) -> str:

    cfg = load_config()
    ssh_args = ["ssh", "-o", "BatchMode=yes", "-o",
                "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=5",
                "-p", str(cfg.bpi_ssh_port)]
    if cfg.bpi_ssh_key:
        ssh_args.extend(["-i", cfg.bpi_ssh_key])
    ssh_args.extend(["--", _ap1_ssh_target(), command])
    result = subprocess.run(ssh_args, capture_output=True, text=True,
                            timeout=timeout, check=False)

    stdout = (
        result.stdout or ""
    ).strip()

    stderr = (
        result.stderr or ""
    ).strip()

    if result.returncode != 0:

        raise RuntimeError(
            "SSH command failed "
            f"(returncode={result.returncode}): "
            f"{stderr or stdout or 'no output'}"
        )

    return stdout


# ============================================================================
# STATION INTERFACE
# ============================================================================


def get_ap1_station_interface(
    station: str,
) -> str | None:

    station_quoted = shlex.quote(
        station
    )

    command = (
        f"STA={station_quoted}; "
        "for IF in "
        "phy0.0-ap0 "
        "phy0.1-ap0 "
        "phy0.2-ap0; "
        "do "
        "/usr/sbin/hostapd_cli "
        "-i \"$IF\" "
        "list_sta "
        "2>/dev/null "
        "| grep -Fqi \"$STA\" "
        "&& echo \"STA_IFACE=$IF\" "
        "&& exit 0; "
        "done; "
        "echo 'STA_IFACE=NONE'"
    )

    output = execute_ap1_ssh(
        command
    )

    match = re.search(
        r"STA_IFACE=(phy0\.[012]-ap0|NONE)",
        output,
    )

    if not match:
        return None

    interface_name = match.group(1)

    if interface_name == "NONE":
        return None

    return interface_name


# ============================================================================
# BAN
# ============================================================================


def ban_station_on_interface(
    station: str,
    interface_name: str,
    ban_time_ms: int = 100000,
) -> str:

    payload = json.dumps(
        {
            "addr": station,
            "deauth": True,
            "ban_time": ban_time_ms,
        },
        separators=(
            ",",
            ":",
        ),
    )

    command = (
        f"ubus call hostapd."
        f"{interface_name} "
        f"del_client "
        f"{shlex.quote(payload)}"
    )

    return execute_ap1_ssh(
        command
    )


def ban_station_on_non_target_bss(
    action: ControlAction,
    ban_time_ms: int = 100000,
) -> dict[str, Any]:

    if not action.station:

        raise ValueError(
            "Station MAC is missing"
        )

    if not action.target_interface:

        raise ValueError(
            "Target interface is missing"
        )

    results: dict[str, Any] = {}

    for radio in action.ap.radios:

        interface_name = (
            radio.interface_name
        )

        if (
            interface_name
            == action.target_interface
        ):
            continue

        try:

            output = (
                ban_station_on_interface(
                    station=action.station,
                    interface_name=interface_name,
                    ban_time_ms=ban_time_ms,
                )
            )

            results[
                interface_name
            ] = {
                "success": True,
                "ban_time_ms": ban_time_ms,
                "stdout": output,
            }

            print(
                "[BAN] "
                f"{action.station} "
                f"on {interface_name} "
                f"for "
                f"{ban_time_ms / 1000:.0f}s"
            )

        except Exception as exc:

            results[
                interface_name
            ] = {
                "success": False,
                "ban_time_ms": ban_time_ms,
                "error": str(exc),
            }

            print(
                "[BAN] ERROR "
                f"{interface_name}: "
                f"{exc}"
            )

    return results


# ============================================================================
# VERIFY
# ============================================================================


def verify_ap1_station_transition(
    action: ControlAction,
    timeout: float = 30.0,
    poll_interval: float = 2.0,
) -> bool:

    if not action.station:
        return False

    if not action.target_interface:
        return False

    deadline = (
        time.monotonic()
        + timeout
    )

    while (
        time.monotonic()
        < deadline
    ):

        try:

            current_interface = (
                get_ap1_station_interface(
                    action.station
                )
            )

            print(
                "[VERIFY] "
                f"STA={action.station} "
                f"current="
                f"{current_interface or 'NONE'} "
                f"target="
                f"{action.target_interface}"
            )

            if (
                current_interface
                == action.target_interface
            ):
                return True

        except Exception as exc:

            print(
                "[VERIFY] "
                f"SSH monitoring error: {exc}"
            )

        time.sleep(
            max(
                0.5,
                poll_interval,
            )
        )

    return False


# ============================================================================
# CONTROL
# ============================================================================


def run_control(
    args: argparse.Namespace,
    config: AppConfig,
) -> int:

    client = OpenWrtClient(
        config
    )

    storage = Storage(
        config.db_path
    )

    storage.init()

    controller = (
        MultiMetricSingleAPController(
            config
        )
    )

    # --------------------------------------------------------------
    # Initialize dashboard state immediately.
    # --------------------------------------------------------------

    controller.last_steering_state = {
        "timestamp": time.time(),
        "status": "starting",
        "devices": [],
    }

    save_steering_state(
        controller
    )

    tag = getattr(
        args,
        "tag",
        None,
    )

    session_id = None

    if tag:

        session_id = storage.start_session(
            tag,
            "control",
            utc_now(),
        )

        print(
            f"[session] control "
            f"'{tag}' started "
            f"(id={session_id})"
        )

    deadline = (
        None
        if args.duration is None
        else (
            time.time()
            + args.duration
        )
    )

    print()
    print(
        "=" * 70
    )

    print(
        " BPI-R4 MULTI-BAND STATION PLACEMENT OPTIMIZER"
    )

    print(
        "=" * 70
    )

    print(
        f"AP           : "
        f"{config.ap.name}"
    )

    print(
        f"Target SSID  : "
        f"{config.target_ssid or 'ALL'}"
    )

    print(
        f"Poll interval: "
        f"{config.poll_interval}s"
    )

    print(
        f"Cooldown     : "
        f"{config.control_cooldown}s"
    )

    print(
        f"Apply mode   : "
        f"{'YES' if args.apply else 'DRY-RUN'}"
    )

    print(
        f"State file   : "
        f"{STEERING_STATE_FILE.resolve()}"
    )

    print(
        "=" * 70
    )

    try:

        while True:

            # ==========================================================
            # COLLECT
            # ==========================================================

            snapshots = collect_iteration(
                client,
                storage,
                config,
                controller=None,
            )

            # ==========================================================
            # DECIDE
            # ==========================================================

            try:

                action = controller.decide(
                    snapshots
                )
                station, radio = controller._find_station(
                    snapshots[config.ap.name]
                )

                if station and radio:
                    metrics = controller._station_metrics(
                        snapshots[config.ap.name],
                        station,
                    )

                    current = metrics.get(
                        radio.band,
                        {},
                    )

                    storage.insert_station_metric(
                        timestamp=utc_now(),
                        station=station,
                        band=radio.band,
                        rssi=current.get("rssi"),
                        clients=current.get("clients"),
                        airtime=current.get("airtime"),
                    )
            except Exception as exc:

                write_steering_error(
                    controller,
                    str(exc),
                )

                print()
                print(
                    "[CONTROLLER ERROR]"
                )

                print(
                    str(exc)
                )

                raise

            # ==========================================================
            # SAVE STATE FOR REACT
            # ==========================================================

            # This is the important part:
            #
            # controller.decide() updates
            # controller.last_steering_state.
            #
            # Flask reads steering_state.json.
            #
            # Therefore save it after EVERY decision cycle,
            # even if action is None.

            try:

                save_steering_state(
                    controller
                )

            except Exception as exc:

                print(
                    "[steering-state] "
                    f"save failed: {exc}"
                )

            # ==========================================================
            # DISPLAY
            # ==========================================================

            print_snapshot(
                snapshots
            )

            print_scores(
                snapshots
            )

            # ==========================================================
            # NO ACTION
            # ==========================================================

            if action is None:

                print(
                    "[idle] "
                    f"{controller.last_skip_reason}"
                )

                if (
                    deadline is not None
                    and time.time()
                    >= deadline
                ):

                    return 0

                interval = (
                    args.interval
                    if args.interval is not None
                    else config.poll_interval
                )

                time.sleep(
                    max(
                        0.1,
                        interval,
                    )
                )

                continue

            # ==========================================================
            # ACTION
            # ==========================================================

            print_decision(
                action
            )

            timestamp = utc_now()

            # ==========================================================
            # DRY RUN
            # ==========================================================

            if not args.apply:

                status = "dry_run"

                response = {
                    "dry_run": True,
                    "command": action.command,
                    "station": action.station,
                    "source_band": action.source_band,
                    "target_band": action.target_band,
                    "source_score": action.score_current,
                    "target_score": action.score_target,
                    "improvement": action.improvement,
                }

                print()
                print(
                    "[DRY-RUN]"
                )

                print(
                    "No command sent to AP1."
                )

            # ==========================================================
            # REAL EXECUTION
            # ==========================================================

            else:

                try:

                    # --------------------------------------------------
                    # PRECHECK
                    # --------------------------------------------------

                    actual_source = (
                        get_ap1_station_interface(
                            action.station
                        )
                    )

                    print(
                        "[PRECHECK] "
                        f"STA={action.station} "
                        f"expected="
                        f"{action.interface_name} "
                        f"actual="
                        f"{actual_source or 'NONE'}"
                    )

                    if (
                        actual_source
                        != action.interface_name
                    ):

                        status = (
                            "stale_decision"
                        )

                        response = {
                            "error": (
                                "Station is no longer "
                                "on the expected source "
                                "interface."
                            ),
                            "expected_source": (
                                action.interface_name
                            ),
                            "actual_source": (
                                actual_source
                            ),
                        }

                        print(
                            "[SKIP] "
                            "Decision is stale."
                        )

                    else:

                        # --------------------------------------------------
                        # BSS TRANSITION
                        # --------------------------------------------------

                        ssh_output = (
                            execute_ap1_ssh(
                                action.command
                            )
                        )

                        print()
                        print(
                            "[BSS-TM] "
                            "command executed."
                        )

                        print(
                            ssh_output
                        )

                        # --------------------------------------------------
                        # BAN NON TARGET BSS
                        # --------------------------------------------------

                        print()
                        print(
                            "[BAN] "
                            "Blocking non-target BSSs..."
                        )

                        ban_results = (
                            ban_station_on_non_target_bss(
                                action=action,
                                ban_time_ms=100000,
                            )
                        )

                        response = {
                            "ssh_target": _ap1_ssh_target(),
                            "command": action.command,
                            "stdout": ssh_output,
                            "ban": ban_results,
                        }

                        # --------------------------------------------------
                        # VERIFY
                        # --------------------------------------------------

                        print()
                        print(
                            "[VERIFY] "
                            "waiting for station transition..."
                        )

                        verified = (
                            verify_ap1_station_transition(
                                action=action,
                                timeout=30.0,
                                poll_interval=2.0,
                            )
                        )

                        if verified:

                            status = (
                                "steering_success"
                            )

                            print()
                            print(
                                "[VERIFY] SUCCESS"
                            )

                            controller.register_steering(
                                action
                            )

                        else:

                            status = (
                                "steering_failed"
                            )

                            print()
                            print(
                                "[VERIFY] FAILED"
                            )

                except Exception as exc:

                    status = "error"

                    response = {
                        "ssh_target": _ap1_ssh_target(),
                        "command": action.command,
                        "error": str(exc),
                    }

                    print()
                    print(
                        "[ERROR]"
                    )

                    print(
                        str(exc)
                    )

            # ==========================================================
            # SAVE STATE AGAIN
            # ==========================================================

            # register_steering() can change cooldown information,
            # so save the state once more after a real steering action.

            try:

                save_steering_state(
                    controller
                )

            except Exception as exc:

                print(
                    "[steering-state] "
                    f"save failed after action: {exc}"
                )

            # ==========================================================
            # STORAGE
            # ==========================================================

            storage.insert_action(
                timestamp,
                action,
                status,
                response,
            )

            print(
                f"[storage] action stored "
                f"status={status}"
            )

            # ==========================================================
            # CONTROL COOLDOWN
            # ==========================================================

            if (
                status
                == "steering_success"
            ):

                cooldown = (
                    config.control_cooldown
                )

            else:

                cooldown = 0

            if cooldown > 0:

                print(
                    f"[cooldown] "
                    f"waiting {cooldown}s..."
                )

                wait_end = (
                    time.time()
                    + cooldown
                )

                while (
                    time.time()
                    < wait_end
                ):

                    if (
                        deadline is not None
                        and time.time()
                        >= deadline
                    ):

                        return 0

                    remaining = (
                        wait_end
                        - time.time()
                    )

                    time.sleep(
                        min(
                            1.0,
                            max(
                                0.0,
                                remaining,
                            ),
                        )
                    )

            # ==========================================================
            # DURATION
            # ==========================================================

            if (
                deadline is not None
                and time.time()
                >= deadline
            ):

                return 0

    except KeyboardInterrupt:

        print()
        print(
            "[stop] Keyboard interrupt."
        )

        controller.last_steering_state = {
            **getattr(
                controller,
                "last_steering_state",
                {},
            ),
            "timestamp": time.time(),
            "status": "stopped",
        }

        try:
            save_steering_state(
                controller
            )
        except Exception as exc:
            print(
                "[steering-state] "
                f"save failed: {exc}"
            )

        return 0

    finally:

        if session_id is not None:

            storage.end_session(
                session_id,
                utc_now(),
            )

            print(
                f"[session] control "
                f"'{tag}' ended "
                f"(id={session_id})"
            )

        storage.close()


# ============================================================================
# COLLECT
# ============================================================================


def run_collect(
    args: argparse.Namespace,
    config: AppConfig,
) -> int:

    client = OpenWrtClient(
        config
    )

    storage = Storage(
        config.db_path
    )

    storage.init()

    controller = (
        MultiMetricSingleAPController(
            config
        )
    )

    deadline = (
        None
        if args.duration is None
        else (
            time.time()
            + args.duration
        )
    )

    try:

        while True:

            snapshots = collect_iteration(
                client,
                storage,
                config,
                controller,
            )

            print_snapshot(
                snapshots
            )

            print_scores(
                snapshots
            )

            if args.once:
                return 0

            if (
                deadline is not None
                and time.time()
                >= deadline
            ):
                return 0

            interval = (
                args.interval
                if args.interval is not None
                else config.poll_interval
            )

            time.sleep(
                max(
                    0.1,
                    interval,
                )
            )

    finally:

        storage.close()


# ============================================================================
# INIT DB
# ============================================================================


def run_init_db(
    args: argparse.Namespace,
    config: AppConfig,
) -> int:

    storage = Storage(
        config.db_path
    )

    try:

        storage.init()

    finally:

        storage.close()

    print(
        json.dumps(
            {
                "db_path": str(
                    config.db_path
                ),
                "status": "initialized",
            },
            indent=2,
        )
    )

    return 0


# ============================================================================
# CONFIG
# ============================================================================


def run_config(
    args: argparse.Namespace,
    config: AppConfig,
) -> int:

    print()
    print(
        "=" * 60
    )

    print(
        " BPI-R4 CONFIGURATION"
    )

    print(
        "=" * 60
    )

    print(
        f"AP name       : "
        f"{config.ap.name}"
    )

    print(
        f"Device ID     : "
        f"{config.ap.device_id}"
    )

    print(
        f"Control ID    : "
        f"{config.ap.control_device_id}"
    )

    print(
        f"Base URL      : "
        f"{config.base_url}"
    )

    print(
        f"Target SSID   : "
        f"{config.target_ssid or 'ALL'}"
    )

    print(
        f"Poll interval : "
        f"{config.poll_interval}s"
    )

    print(
        f"Cooldown      : "
        f"{config.control_cooldown}s"
    )

    print()
    print(
        "Score weights:"
    )

    print(
        f"  clients     : "
        f"{config.weight_clients}"
    )

    print(
        f"  RSSI        : "
        f"{config.weight_rssi}"
    )

    print(
        f"  airtime     : "
        f"{config.weight_airtime}"
    )

    print(
        f"  throughput  : "
        f"{config.weight_throughput}"
    )

    print(
        f"  TX power    : "
        f"{config.weight_txpower}"
    )

    print()
    print(
        "Radios:"
    )

    for radio in config.ap.radios:

        print(
            f"  {radio.band:<3} "
            f"iface="
            f"{radio.interface_name:<20} "
            f"uci="
            f"{radio.uci_radio}"
        )

    print(
        "=" * 60
    )

    return 0


# ============================================================================
# SYNC SESSIONS
# ============================================================================


def run_sync_sessions(
    args: argparse.Namespace,
    config: AppConfig,
) -> int:

    client = OpenWrtClient(
        config
    )

    storage = Storage(
        config.db_path
    )

    storage.init()

    filters: dict[
        str,
        Any,
    ] = {}

    if args.device_id:

        filters[
            "device"
        ] = args.device_id

    if args.start:

        filters[
            "start_time"
        ] = args.start

    if args.stop:

        filters[
            "stop_time"
        ] = args.stop

    try:

        print(
            "[sync] Fetching Wi-Fi sessions..."
        )

        sessions = (
            client.list_wifi_sessions(
                **filters
            )
        )

        storage.upsert_wifi_sessions(
            sessions
        )

        print(
            json.dumps(
                {
                    "stored_sessions": len(
                        sessions
                    ),
                    "filters": filters,
                },
                indent=2,
            )
        )

        return 0

    finally:

        storage.close()


# ============================================================================
# EXPORT
# ============================================================================


def run_export(
    args: argparse.Namespace,
    config: AppConfig,
) -> int:

    storage = Storage(
        config.db_path
    )

    storage.init()

    try:

        storage.export_radio_metrics_csv(
            args.output,
            interface_name=args.interface,
        )

    finally:

        storage.close()

    print(
        json.dumps(
            {
                "output": str(
                    args.output
                ),
                "interface": args.interface,
            },
            indent=2,
        )
    )

    return 0


# ============================================================================
# ARGUMENT PARSER
# ============================================================================


def str_to_path(
    value: str,
) -> Path:

    return Path(
        value
    )


def build_parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "OpenWrt BPI-R4 "
            "single-AP multi-radio "
            "station-placement optimizer"
        )
    )

    subparsers = (
        parser.add_subparsers(
            dest="command",
            required=True,
        )
    )

    # ------------------------------------------------------------------
    # init-db
    # ------------------------------------------------------------------

    init_db = subparsers.add_parser(
        "init-db",
        help="Create or migrate SQLite schema",
    )

    init_db.set_defaults(
        func=run_init_db
    )

    # ------------------------------------------------------------------
    # config
    # ------------------------------------------------------------------

    config_cmd = subparsers.add_parser(
        "config",
        help="Display effective configuration",
    )

    config_cmd.set_defaults(
        func=run_config
    )

    # ------------------------------------------------------------------
    # collect
    # ------------------------------------------------------------------

    collect = subparsers.add_parser(
        "collect",
        help="Collect BPI-R4 monitoring snapshots",
    )

    collect.add_argument(
        "--once",
        action="store_true",
        help="Collect one snapshot",
    )

    collect.add_argument(
        "--duration",
        type=int,
        help="Collection duration in seconds",
    )

    collect.add_argument(
        "--interval",
        type=float,
        help="Polling interval in seconds",
    )

    collect.add_argument(
        "--tag",
        help="Experiment tag",
    )

    collect.set_defaults(
        func=run_collect
    )

    # ------------------------------------------------------------------
    # run
    # ------------------------------------------------------------------

    control = subparsers.add_parser(
        "run",
        help=(
            "Run multi-band station-placement "
            "optimizer"
        ),
    )

    control.add_argument(
        "--duration",
        type=int,
        help="Run duration in seconds",
    )

    control.add_argument(
        "--interval",
        type=float,
        help=(
            "Polling interval when no "
            "steering decision exists"
        ),
    )

    control.add_argument(
        "--apply",
        action="store_true",
        help=(
            "Execute BSS-TM commands on AP1. "
            "Without this flag the controller "
            "runs in dry-run."
        ),
    )

    control.add_argument(
        "--tag",
        help="Experiment tag",
    )

    control.set_defaults(
        func=run_control
    )

    # ------------------------------------------------------------------
    # sync sessions
    # ------------------------------------------------------------------

    sync_sessions = subparsers.add_parser(
        "sync-sessions",
        help="Sync currently associated OpenWrt stations",
    )

    sync_sessions.add_argument(
        "--device-id",
        help="Local AP identifier",
    )

    sync_sessions.add_argument(
        "--start",
        help="Start time filter",
    )

    sync_sessions.add_argument(
        "--stop",
        help="Stop time filter",
    )

    sync_sessions.set_defaults(
        func=run_sync_sessions
    )

    # ------------------------------------------------------------------
    # export
    # ------------------------------------------------------------------

    export = subparsers.add_parser(
        "export-csv",
        help="Export radio time-series to CSV",
    )

    export.add_argument(
        "--interface",
        help="Optional interface filter",
    )

    export.add_argument(
        "--output",
        required=True,
        type=str_to_path,
        help="Output CSV path",
    )

    export.set_defaults(
        func=run_export
    )

    return parser


# ============================================================================
# MAIN
# ============================================================================


def main(
    argv: list[str] | None = None,
) -> int:

    parser = build_parser()

    args = parser.parse_args(
        argv
    )

    try:

        config = load_config()

    except ValueError as exc:

        parser.error(
            str(exc)
        )

        return 2

    if getattr(args, "apply", False) and not config.bpi_allow_changes:
        parser.error("--apply also requires BPI_ALLOW_CHANGES=true in .env")

    return args.func(
        args,
        config,
    )


if __name__ == "__main__":

    raise SystemExit(
        main()
    )
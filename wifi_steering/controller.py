from __future__ import annotations

import math
import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from typing import Any

from .device_rules import BANDS, DeviceRuleStore


# ============================================================================
# CONSTANTS
# ============================================================================

WIFI_INTERFACES = {
    "phy0.0-ap0": "2G",
    "phy0.1-ap0": "5G",
    "phy0.2-ap0": "6G",
}

DEFAULT_BPI_HOST = "192.168.1.10"
DEFAULT_BPI_USER = "root"
DEFAULT_BPI_PORT = 22

VALID_BANDS = ("2G", "5G", "6G")


# ============================================================================
# HELPERS
# ============================================================================


def _clamp(
    value: float,
    minimum: float = 0.0,
    maximum: float = 1.0,
) -> float:
    return max(
        minimum,
        min(maximum, value),
    )


def _safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        if value is None:
            return default

        value = float(value)

        if math.isnan(value) or math.isinf(value):
            return default

        return value

    except (TypeError, ValueError):
        return default


def _safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        if value is None:
            return default

        return int(float(value))

    except (TypeError, ValueError):
        return default


def _normalize_mac(
    mac: str,
) -> str:
    value = (
        str(mac or "")
        .strip()
        .lower()
        .replace("-", ":")
    )

    return value


def _band_from_interface(
    interface_name: str,
) -> str:
    return WIFI_INTERFACES.get(
        str(interface_name or "").strip(),
        "UNKNOWN",
    )


def _is_wifi_interface(
    interface_name: str,
) -> bool:
    return (
        str(interface_name or "").strip()
        in WIFI_INTERFACES
    )


def _get_value(
    data: dict[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    for key in keys:
        if key in data:
            return data[key]

    return default


def _extract_station_mac(
    client: dict[str, Any],
) -> str | None:
    value = _get_value(
        client,
        "mac",
        "mac_address",
        "station_mac",
        "station",
        "address",
        default=None,
    )

    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    return _normalize_mac(value)


def _round_dict(
    values: dict[str, float],
    digits: int = 4,
) -> dict[str, float]:
    return {
        key: round(
            _safe_float(value),
            digits,
        )
        for key, value in values.items()
    }


# ============================================================================
# RADIO STATE
# ============================================================================


@dataclass
class RadioState:

    ap_id: str = ""
    ap_name: str = ""

    interface_name: str = ""
    band: str = ""

    ssid: str = ""

    channel: int | None = None
    frequency: int | None = None

    tx_power: int | None = None
    noise: int | None = None

    htmode: str = ""

    up: bool = True

    client_count: int = 0
    avg_signal: float | None = None
    total_airtime: float = 0.0

    rx_bytes: int = 0
    tx_bytes: int = 0

    rx_packets: int = 0
    tx_packets: int = 0

    clients: list[dict[str, Any]] = field(
        default_factory=list
    )

    channel_utilization: float = 0.0

    throughput_mbps: float = 0.0
    packet_loss: float = 0.0
    latency_ms: float = 0.0
    interface_load: float = 0.0

    # Diagnostic radio score.
    #
    # IMPORTANT:
    # This is NOT the station steering score.
    # Station steering uses DeviceBandController.decide_band().
    score: float = 0.0

    raw: dict[str, Any] = field(
        default_factory=dict
    )


# ============================================================================
# AP STATE
# ============================================================================


@dataclass
class APState:

    name: str
    device_id: str
    control_device_id: str

    radios: tuple[Any, ...] = field(
        default_factory=tuple
    )


# ============================================================================
# CONTROL ACTION
# ============================================================================


@dataclass
class ControlAction:

    ap: APState

    station: str | None

    interface_name: str
    band: str

    source_band: str | None

    target_band: str | None
    target_interface: str | None
    target_bssid: str | None

    score_current: float
    score_target: float
    improvement: float

    action_type: str

    old_value: int | None = None
    new_value: int | None = None

    reason: str = ""

    command: str = ""


# ============================================================================
# OPENWISP SNAPSHOT NORMALIZATION
# ============================================================================


def _extract_clients(
    raw_radio: dict[str, Any],
) -> list[dict[str, Any]]:

    clients = _get_value(
        raw_radio,
        "clients",
        "stations",
        "associated_clients",
        "stas",
        default=[],
    )

    if isinstance(clients, dict):

        result: list[dict[str, Any]] = []

        for mac, value in clients.items():

            if isinstance(value, dict):
                item = dict(value)
            else:
                item = {
                    "value": value,
                }

            item.setdefault(
                "mac",
                mac,
            )

            result.append(item)

        return result

    if isinstance(clients, list):

        return [
            item
            for item in clients
            if isinstance(item, dict)
        ]

    return []


def _normalize_radio(
    raw_radio: Any,
    config,
    ap,
) -> RadioState | None:

    if isinstance(raw_radio, RadioState):
        return raw_radio

    if not isinstance(raw_radio, dict):
        return None

    interface_name = str(
        _get_value(
            raw_radio,
            "interface_name",
            "interface",
            "ifname",
            "name",
            default="",
        )
        or ""
    ).strip()

    band = str(
        _get_value(
            raw_radio,
            "band",
            default="",
        )
        or ""
    ).upper()

    if not band or band == "UNKNOWN":
        band = _band_from_interface(
            interface_name
        )

    # Ignore OpenWISP non-Wi-Fi interfaces:
    # lan1, br-lan, wan, eth0, etc.
    if band not in VALID_BANDS:
        return None

    clients = _extract_clients(
        raw_radio
    )

    client_count = _safe_int(
        _get_value(
            raw_radio,
            "client_count",
            "clients_count",
            "station_count",
            "num_clients",
            default=len(clients),
        ),
        len(clients),
    )

    avg_signal = _get_value(
        raw_radio,
        "avg_signal",
        "rssi",
        "signal",
        "average_signal",
        default=None,
    )

    if avg_signal is not None:
        avg_signal = _safe_float(
            avg_signal,
            -100.0,
        )

    airtime = _safe_float(
        _get_value(
            raw_radio,
            "total_airtime",
            "airtime",
            "airtime_percent",
            "channel_utilization",
            default=0,
        ),
        0,
    )

    airtime = _clamp(
        airtime,
        0.0,
        100.0,
    )

    throughput = _safe_float(
        _get_value(
            raw_radio,
            "throughput_mbps",
            "throughput",
            "bitrate_mbps",
            default=0.0,
        ),
        0,
    )

    tx_power = _get_value(
        raw_radio,
        "tx_power",
        "txpower",
        "tx_power_dbm",
        default=None,
    )

    if tx_power is not None:
        tx_power = _safe_int(
            tx_power
        )

    channel = _get_value(
        raw_radio,
        "channel",
        default=None,
    )

    if channel is not None:
        channel = _safe_int(
            channel
        )

    frequency = _get_value(
        raw_radio,
        "frequency",
        "freq",
        default=None,
    )

    if frequency is not None:
        frequency = _safe_int(
            frequency
        )

    noise = _get_value(
        raw_radio,
        "noise",
        default=None,
    )

    if noise is not None:
        noise = _safe_int(
            noise
        )

    return RadioState(
        ap_id=str(
            getattr(
                ap,
                "device_id",
                "",
            )
        ),
        ap_name=str(
            getattr(
                ap,
                "name",
                "",
            )
        ),
        interface_name=interface_name,
        band=band,
        ssid=str(
            _get_value(
                raw_radio,
                "ssid",
                default="",
            )
            or ""
        ),
        channel=channel,
        frequency=frequency,
        tx_power=tx_power,
        noise=noise,
        htmode=str(
            _get_value(
                raw_radio,
                "htmode",
                "mode",
                default="",
            )
            or ""
        ),
        up=bool(
            _get_value(
                raw_radio,
                "up",
                "enabled",
                default=True,
            )
        ),
        client_count=max(
            0,
            client_count,
        ),
        avg_signal=avg_signal,
        total_airtime=airtime,
        rx_bytes=max(
            0,
            _safe_int(
                _get_value(
                    raw_radio,
                    "rx_bytes",
                    default=0,
                )
            ),
        ),
        tx_bytes=max(
            0,
            _safe_int(
                _get_value(
                    raw_radio,
                    "tx_bytes",
                    default=0,
                )
            ),
        ),
        rx_packets=max(
            0,
            _safe_int(
                _get_value(
                    raw_radio,
                    "rx_packets",
                    default=0,
                )
            ),
        ),
        tx_packets=max(
            0,
            _safe_int(
                _get_value(
                    raw_radio,
                    "tx_packets",
                    default=0,
                )
            ),
        ),
        clients=clients,
        channel_utilization=airtime,
        throughput_mbps=max(
            0.0,
            throughput,
        ),
        packet_loss=max(
            0.0,
            _safe_float(
                _get_value(
                    raw_radio,
                    "packet_loss",
                    default=0.0,
                ),
                0,
            ),
        ),
        latency_ms=max(
            0.0,
            _safe_float(
                _get_value(
                    raw_radio,
                    "latency_ms",
                    "latency",
                    default=0.0,
                ),
                0,
            ),
        ),
        interface_load=max(
            0.0,
            _safe_float(
                _get_value(
                    raw_radio,
                    "interface_load",
                    "load",
                    default=0.0,
                ),
                0,
            ),
        ),
        score=0.0,
        raw=dict(raw_radio),
    )


def normalize_snapshot(
    raw_snapshot: Any,
    config,
    ap,
) -> dict[str, Any]:

    raw = raw_snapshot

    radios_raw: Any = []

    if isinstance(
        raw_snapshot,
        dict,
    ):

        radios_raw = _get_value(
            raw_snapshot,
            "radios",
            "radio",
            "interfaces",
            "wireless",
            "results",
            default=[],
        )

        if isinstance(
            radios_raw,
            dict,
        ):
            radios_raw = list(
                radios_raw.values()
            )

    elif isinstance(
        raw_snapshot,
        list,
    ):

        radios_raw = raw_snapshot

    if not isinstance(
        radios_raw,
        list,
    ):
        radios_raw = []

    radios: list[RadioState] = []

    for raw_radio in radios_raw:

        radio = _normalize_radio(
            raw_radio,
            config,
            ap,
        )

        if radio is not None:
            radios.append(radio)

    # --------------------------------------------------------------
    # Guarantee configured Wi-Fi radios exist.
    # --------------------------------------------------------------

    existing_interfaces = {
        radio.interface_name
        for radio in radios
    }

    for configured_radio in getattr(
        ap,
        "radios",
        (),
    ):

        interface_name = str(
            getattr(
                configured_radio,
                "interface_name",
                "",
            )
            or ""
        ).strip()

        if not interface_name:
            continue

        if interface_name in existing_interfaces:
            continue

        band = str(
            getattr(
                configured_radio,
                "band",
                _band_from_interface(
                    interface_name
                ),
            )
            or ""
        ).upper()

        if band not in VALID_BANDS:
            continue

        radios.append(
            RadioState(
                ap_id=str(
                    getattr(
                        ap,
                        "device_id",
                        "",
                    )
                ),
                ap_name=str(
                    getattr(
                        ap,
                        "name",
                        "",
                    )
                ),
                interface_name=interface_name,
                band=band,
                up=True,
                raw={},
            )
        )

    return {
        "ap_id": getattr(
            ap,
            "device_id",
            "",
        ),
        "ap_name": getattr(
            ap,
            "name",
            "",
        ),
        "radios": radios,
        "raw": raw,
    }


# ============================================================================
# DEVICE BAND CONTROLLER
# ============================================================================


class DeviceBandController:

    def __init__(
        self,
        config,
    ):

        self.config = config

        self.rules = DeviceRuleStore(
            config.device_rules_path
        )

        # MAC -> monotonic timestamp
        self._last_switch: dict[
            str,
            float,
        ] = {}

    # ==================================================================
    # DEFAULT RULE
    # ==================================================================

    def _default_rule(
        self,
        mac: str,
    ) -> dict[str, Any]:

        return {
            "mac": mac,

            "device_type": "Unknown",

            "priority": "medium",

            "bands": {
                "2G": True,
                "5G": True,
                "6G": True,
            },

            "preferred_band": "5G",

            # These are only fallback values.
            # Backend recalculates them from requirements.
            "weights": {
                "clients": getattr(
                    self.config,
                    "weight_clients",
                    0.20,
                ),
                "rssi": getattr(
                    self.config,
                    "weight_rssi",
                    0.20,
                ),
                "airtime": getattr(
                    self.config,
                    "weight_airtime",
                    0.20,
                ),
                "throughput": getattr(
                    self.config,
                    "weight_throughput",
                    0.20,
                ),
                "txpower": getattr(
                    self.config,
                    "weight_txpower",
                    0.20,
                ),
            },

            "thresholds": {
                "2G": {
                    "min_rssi": getattr(
                        self.config,
                        "default_min_rssi_2g",
                        -75,
                    ),
                },
                "5G": {
                    "min_rssi": getattr(
                        self.config,
                        "default_min_rssi_5g",
                        -70,
                    ),
                },
                "6G": {
                    "min_rssi": getattr(
                        self.config,
                        "default_min_rssi_6g",
                        -65,
                    ),
                },
            },

            "min_throughput_mbps": getattr(
                self.config,
                "default_min_throughput_mbps",
                5,
            ),

            "max_airtime_percent": getattr(
                self.config,
                "default_max_airtime_percent",
                80,
            ),

            "switch_threshold": getattr(
                self.config,
                "default_switch_threshold",
                1,
            ),

            "cooldown": getattr(
                self.config,
                "default_rule_cooldown",
                60,
            ),
        }

    # ==================================================================
    # RULE LOADING
    # ==================================================================

    def get_rule(
        self,
        mac: str,
    ) -> dict[str, Any]:

        mac = _normalize_mac(
            mac
        )

        stored = self.rules.get(
            mac
        )

        defaults = self._default_rule(
            mac
        )

        if not stored:

            defaults["weights"] = (
                self._derive_weights(
                    defaults
                )
            )

            return defaults

        rule = dict(
            defaults
        )

        rule.update(
            stored
        )

        rule["bands"] = {
            **defaults["bands"],
            **(
                stored.get(
                    "bands",
                    {},
                )
                or {}
            ),
        }

        rule["weights"] = {
            **defaults["weights"],
            **(
                stored.get(
                    "weights",
                    {},
                )
                or {}
            ),
        }

        rule["thresholds"] = {
            **defaults["thresholds"],
            **(
                stored.get(
                    "thresholds",
                    {},
                )
                or {}
            ),
        }

        for band in VALID_BANDS:

            rule["thresholds"][band] = {
                **defaults["thresholds"][band],
                **(
                    rule["thresholds"].get(
                        band,
                        {},
                    )
                    or {}
                ),
            }

        # Backend is authoritative.
        rule["weights"] = (
            self._derive_weights(
                rule
            )
        )

        return rule

    # ==================================================================
    # SAVE RULE
    # ==================================================================

    def save_rule(
        self,
        mac: str,
        rule: dict[str, Any],
    ) -> dict[str, Any]:

        mac = _normalize_mac(
            mac
        )

        rule = dict(
            rule
        )

        rule["mac"] = mac

        # Never trust frontend weights.
        rule["weights"] = (
            self._derive_weights(
                rule
            )
        )

        return self.rules.save(
            mac,
            rule,
        )

    # ==================================================================
    # ALL RULES
    # ==================================================================

    def get_all_rules(
        self,
    ) -> dict[str, dict[str, Any]]:

        rules = self.rules.get_all()

        result = {}

        for mac, rule in rules.items():

            normalized_mac = (
                _normalize_mac(
                    mac
                )
            )

            normalized_rule = dict(
                rule
            )

            normalized_rule["weights"] = (
                self._derive_weights(
                    normalized_rule
                )
            )

            result[normalized_mac] = (
                normalized_rule
            )

        return result

    # ==================================================================
    # AUTOMATIC WEIGHTS
    # ==================================================================

    def _derive_weights(
        self,
        rule: dict[str, Any],
    ) -> dict[str, float]:
        """
        Automatically derive metric weights from the client's
        requirements.

        IMPORTANT:
            preferred_band is NOT used here.

        preferred_band is a band preference and is handled separately
        as a small score bonus.
        """

        weights = {
            "clients": 0.20,
            "rssi": 0.20,
            "airtime": 0.20,
            "throughput": 0.20,
            "txpower": 0.20,
        }

        thresholds = (
            rule.get(
                "thresholds",
                {},
            )
            or {}
        )

        enabled_bands = (
            rule.get(
                "bands",
                {},
            )
            or {}
        )

        # --------------------------------------------------------------
        # RSSI requirement
        # --------------------------------------------------------------

        rssi_values = []

        for band in VALID_BANDS:

            if not enabled_bands.get(
                band,
                True,
            ):
                continue

            value = (
                thresholds
                .get(
                    band,
                    {},
                )
                .get(
                    "min_rssi",
                    -70,
                )
            )

            rssi_values.append(
                _safe_float(
                    value,
                    -70,
                )
            )

        if rssi_values:

            # Less negative = stricter.
            strictest_rssi = max(
                rssi_values
            )

            if strictest_rssi >= -60:

                weights["rssi"] += 0.25

            elif strictest_rssi >= -65:

                weights["rssi"] += 0.20

            elif strictest_rssi >= -70:

                weights["rssi"] += 0.10

        # --------------------------------------------------------------
        # Throughput requirement
        # --------------------------------------------------------------

        min_throughput = _safe_float(
            rule.get(
                "min_throughput_mbps",
                0,
            ),
            0,
        )

        if min_throughput >= 100:

            weights["throughput"] += 0.30

        elif min_throughput >= 50:

            weights["throughput"] += 0.25

        elif min_throughput >= 20:

            weights["throughput"] += 0.15

        elif min_throughput >= 10:

            weights["throughput"] += 0.08

        # --------------------------------------------------------------
        # Airtime requirement
        # --------------------------------------------------------------

        max_airtime = _safe_float(
            rule.get(
                "max_airtime_percent",
                80,
            ),
            80,
        )

        if max_airtime <= 40:

            weights["airtime"] += 0.30

        elif max_airtime <= 50:

            weights["airtime"] += 0.25

        elif max_airtime <= 60:

            weights["airtime"] += 0.15

        elif max_airtime <= 70:

            weights["airtime"] += 0.08

        # --------------------------------------------------------------
        # Device type
        # --------------------------------------------------------------

        device_type = str(
            rule.get(
                "device_type",
                "Unknown",
            )
            or "Unknown"
        ).strip()

        if device_type == "TV/Streaming":

            weights["throughput"] += 0.15
            weights["airtime"] += 0.05

        elif device_type == "Camera":

            weights["throughput"] += 0.10
            weights["rssi"] += 0.10

        elif device_type in {
            "Smartphone",
            "Tablet",
        }:

            weights["rssi"] += 0.05
            weights["throughput"] += 0.05

        elif device_type in {
            "PC",
            "Laptop/Desktop",
        }:

            weights["throughput"] += 0.10
            weights["rssi"] += 0.05

        elif device_type in {
            "IoT",
            "Printer",
            "Robot",
        }:

            weights["rssi"] += 0.05
            weights["clients"] += 0.05

        elif device_type == "Router":

            weights["airtime"] += 0.10
            weights["clients"] += 0.05

        # --------------------------------------------------------------
        # Priority
        # --------------------------------------------------------------

        priority = str(
            rule.get(
                "priority",
                "medium",
            )
            or "medium"
        ).lower()

        if priority == "critical":

            weights["rssi"] += 0.10
            weights["throughput"] += 0.10
            weights["airtime"] += 0.05

        elif priority == "high":

            weights["rssi"] += 0.07
            weights["throughput"] += 0.07
            weights["airtime"] += 0.03

        elif priority == "low":

            weights["clients"] += 0.05
            weights["txpower"] += 0.05

        # --------------------------------------------------------------
        # Normalize
        # --------------------------------------------------------------

        total = sum(
            max(
                0.0,
                value,
            )
            for value in weights.values()
        )

        if total <= 0:

            return {
                "clients": 0.20,
                "rssi": 0.20,
                "airtime": 0.20,
                "throughput": 0.20,
                "txpower": 0.20,
            }

        normalized = {
            key: value / total
            for key, value in weights.items()
        }

        # Make the sum exactly 1.0.
        normalized = _round_dict(
            normalized,
            4,
        )

        difference = round(
            1.0
            - sum(
                normalized.values()
            ),
            4,
        )

        normalized["throughput"] = round(
            normalized["throughput"]
            + difference,
            4,
        )

        return normalized

    # ==================================================================
    # BAND SCORE
    # ==================================================================

    def _band_score(
        self,
        band: str,
        metrics: dict[str, Any],
        rule: dict[str, Any],
        max_clients: int = 1,
    ) -> tuple[float, bool, str]:
        """
        Calculate the quality of one candidate band for one station.

        Score:
            0..100

        Hard requirements:
            - band enabled
            - known RSSI >= minimum
            - known airtime <= maximum

        Soft criteria:
            - RSSI quality
            - airtime
            - throughput
            - client load
            - TX power

        Unknown candidate measurements are neutral.
        """

        band = str(
            band or ""
        ).upper()

        # --------------------------------------------------------------
        # Band enabled
        # --------------------------------------------------------------

        if not rule.get(
            "bands",
            {},
        ).get(
            band,
            False,
        ):

            return (
                0.0,
                False,
                "Band disabled by device rule.",
            )

        # --------------------------------------------------------------
        # Read metrics
        # --------------------------------------------------------------

        rssi = metrics.get(
            "rssi"
        )

        rssi_known = bool(
            metrics.get(
                "rssi_known",
                rssi is not None,
            )
        )

        throughput = metrics.get(
            "throughput_mbps"
        )

        throughput_known = bool(
            metrics.get(
                "throughput_known",
                throughput is not None,
            )
        )

        airtime = metrics.get(
            "airtime"
        )

        airtime_known = bool(
            metrics.get(
                "airtime_known",
                airtime is not None,
            )
        )

        clients = max(
            0,
            _safe_int(
                metrics.get(
                    "clients",
                    0,
                ),
                0,
            ),
        )

        txpower = metrics.get(
            "txpower"
        )

        # --------------------------------------------------------------
        # RSSI
        # --------------------------------------------------------------

        min_rssi = _safe_float(
            rule.get(
                "thresholds",
                {},
            )
            .get(
                band,
                {},
            )
            .get(
                "min_rssi",
                -70,
            ),
            -70,
        )

        if (
            rssi_known
            and rssi is not None
        ):

            rssi = _safe_float(
                rssi,
                -100,
            )

            if rssi < min_rssi:

                return (
                    0.0,
                    False,
                    (
                        f"RSSI {rssi:.1f} dBm < "
                        f"minimum {min_rssi:.1f} dBm"
                    ),
                )

            # -90 => 0
            # -50 => 1
            rssi_score = _clamp(
                (rssi + 90.0) / 40.0
            )

        else:

            # Candidate band has no station-specific RSSI.
            # Neutral rather than fake-bad.
            rssi_score = 0.5

        # --------------------------------------------------------------
        # Airtime
        # --------------------------------------------------------------

        max_airtime = _safe_float(
            rule.get(
                "max_airtime_percent",
                80,
            ),
            80,
        )

        if (
            airtime_known
            and airtime is not None
        ):

            airtime = _clamp(
                _safe_float(
                    airtime,
                    0,
                ),
                0.0,
                100.0,
            )

            if airtime > max_airtime:

                return (
                    0.0,
                    False,
                    (
                        f"Airtime {airtime:.1f}% > "
                        f"maximum {max_airtime:.1f}%"
                    ),
                )

            airtime_score = (
                1.0
                - (
                    airtime
                    / 100.0
                )
            )

        else:

            airtime_score = 0.5

        # --------------------------------------------------------------
        # Throughput
        # --------------------------------------------------------------

        min_throughput = _safe_float(
            rule.get(
                "min_throughput_mbps",
                0,
            ),
            0,
        )

        if (
            throughput_known
            and throughput is not None
            and min_throughput > 0
        ):

            throughput = max(
                0.0,
                _safe_float(
                    throughput,
                    0,
                ),
            )

            # SOFT criterion.
            #
            # 10 Mbps / 20 Mbps requirement = 0.50.
            # It does NOT reject the band.
            throughput_score = _clamp(
                throughput
                / min_throughput
            )

        else:

            # Unknown throughput is neutral.
            throughput_score = 0.5

        # --------------------------------------------------------------
        # Client load
        # --------------------------------------------------------------

        max_clients = max(
            1,
            int(max_clients or 1),
        )

        clients_score = _clamp(
            1.0
            - (
                float(clients)
                / float(max_clients)
            )
        )

        # --------------------------------------------------------------
        # TX power
        # --------------------------------------------------------------

        if txpower is not None:

            txpower_value = _safe_float(
                txpower,
                0,
            )

            tx_min = _safe_float(
                getattr(
                    self.config,
                    "tx_power_min",
                    getattr(
                        self.config,
                        "min_txpower",
                        8,
                    ),
                ),
                8,
            )

            tx_max = _safe_float(
                getattr(
                    self.config,
                    "tx_power_max",
                    getattr(
                        self.config,
                        "max_txpower",
                        30,
                    ),
                ),
                30,
            )

            if tx_max > tx_min:

                txpower_score = _clamp(
                    (
                        txpower_value
                        - tx_min
                    )
                    / (
                        tx_max
                        - tx_min
                    )
                )

            else:

                txpower_score = 0.5

        else:

            txpower_score = 0.5

        # --------------------------------------------------------------
        # Automatic weights
        # --------------------------------------------------------------

        weights = self._derive_weights(
            rule
        )

        score = (
            weights["rssi"]
            * rssi_score

            + weights["airtime"]
            * airtime_score

            + weights["throughput"]
            * throughput_score

            + weights["clients"]
            * clients_score

            + weights["txpower"]
            * txpower_score
        )

        score *= 100.0

        # --------------------------------------------------------------
        # Preferred band
        # --------------------------------------------------------------

        preferred_band = str(
            rule.get(
                "preferred_band",
                "",
            )
            or ""
        ).upper()

        if (
            preferred_band
            and band == preferred_band
        ):

            # Preference only.
            score += 5.0

        score = _clamp(
            score,
            0.0,
            100.0,
        )

        return (
            round(
                score,
                2,
            ),
            True,
            "Band satisfies the requirements.",
        )

    # ==================================================================
    # DECIDE BAND
    # ==================================================================

    def decide_band(
        self,
        mac: str,
        current_band: str,
        metrics: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:

        mac = _normalize_mac(
            mac
        )

        rule = self.get_rule(
            mac
        )

        current_band = str(
            current_band or ""
        ).upper()

        weights = self._derive_weights(
            rule
        )

        scores: dict[str, float] = {}

        eligible_bands: list[str] = []

        rejection_reasons: dict[
            str,
            str,
        ] = {}

        # --------------------------------------------------------------
        # Relative client load
        # --------------------------------------------------------------

        max_clients = max(
            1,
            *[
                _safe_int(
                    value.get(
                        "clients",
                        0,
                    ),
                    0,
                )
                for value in metrics.values()
                if isinstance(
                    value,
                    dict,
                )
            ],
        )

        # --------------------------------------------------------------
        # Score all bands
        # --------------------------------------------------------------

        for band in VALID_BANDS:

            if not rule.get(
                "bands",
                {},
            ).get(
                band,
                True,
            ):

                scores[band] = 0.0

                rejection_reasons[band] = (
                    "Band disabled by device rule."
                )

                continue

            band_metrics = metrics.get(
                band
            )

            if not isinstance(
                band_metrics,
                dict,
            ):

                scores[band] = 0.0

                rejection_reasons[band] = (
                    "No metrics available."
                )

                continue

            (
                score,
                eligible,
                reason,
            ) = self._band_score(
                band=band,
                metrics=band_metrics,
                rule=rule,
                max_clients=max_clients,
            )

            scores[band] = score

            if eligible:

                eligible_bands.append(
                    band
                )

            else:

                rejection_reasons[band] = (
                    reason
                )

        # --------------------------------------------------------------
        # Current score
        # --------------------------------------------------------------

        current_score = _safe_float(
            scores.get(
                current_band,
                0.0,
            ),
            0.0,
        )

        # --------------------------------------------------------------
        # Best band
        # --------------------------------------------------------------

        if eligible_bands:

            best_band = max(
                eligible_bands,
                key=lambda item: scores.get(
                    item,
                    0.0,
                ),
            )

        else:

            best_band = current_band

        best_score = _safe_float(
            scores.get(
                best_band,
                0.0,
            ),
            0.0,
        )

        improvement = (
            best_score
            - current_score
        )

        # --------------------------------------------------------------
        # Switch threshold
        # --------------------------------------------------------------

        switch_threshold = _safe_float(
            rule.get(
                "switch_threshold",
                getattr(
                    self.config,
                    "default_switch_threshold",
                    1,
                ),
            ),
            1,
        )

        # --------------------------------------------------------------
        # Cooldown
        # --------------------------------------------------------------

        # Minimum cooldown: 60 seconds per station (see max below).
        # A rule may request a longer cooldown, but never a shorter one.
        configured_cooldown = _safe_float(
            rule.get(
                "cooldown",
                getattr(
                    self.config,
                    "default_rule_cooldown",
                    60,
                ),
            ),
            60,
        )

        cooldown = max(
            60.0,
            configured_cooldown,
        )
        now = time.monotonic()

        last_switch = (
            self._last_switch.get(
                mac
            )
        )

        cooldown_remaining = 0.0

        if last_switch is not None:

            elapsed = (
                now
                - last_switch
            )

            cooldown_remaining = max(
                0.0,
                cooldown
                - elapsed,
            )

        # --------------------------------------------------------------
        # Current band eligibility
        # --------------------------------------------------------------

        current_invalid = (
            current_band
            not in eligible_bands
        )

        current_rejection = (
            rejection_reasons.get(
                current_band,
                "",
            )
        )

        # Only real hard constraints may bypass cooldown.
        hard_current_failure = (
            current_rejection.startswith(
                "RSSI "
            )
            or current_rejection.startswith(
                "Airtime "
            )
            or current_rejection.startswith(
                "Band disabled"
            )
        )
        # Strict per-station cooldown: no steering before expiry.
        if cooldown_remaining > 0:
            changed = False
            decision_reason = (
                f"Steering blocked by cooldown: "
                f"{cooldown_remaining:.1f}s remaining."
            )
        else:
            changed = False
            decision_reason = ""
        changed = False

        # ==============================================================
        # CASE 1: Current band violates a hard requirement
        # Cooldown must never be bypassed.
        # ==============================================================

        if (
            current_invalid
            and hard_current_failure
            and best_band != current_band
            and best_band in eligible_bands
        ):

            if cooldown_remaining > 0:

                changed = False

                decision_reason = (
                    f"Steering blocked by cooldown: "
                    f"{cooldown_remaining:.1f}s remaining. "
                    f"Current band {current_band} violates "
                    f"a hard requirement: {current_rejection}."
                )

            else:

                changed = True

                decision_reason = (
                    f"Current band {current_band} "
                    f"violates a hard requirement: "
                    f"{current_rejection}. "
                    f"Moving to {best_band}."
                )
        # ==============================================================
        # CASE 2: Current band not eligible, but no hard failure
        # ==============================================================

        elif (
            current_invalid
            and best_band != current_band
            and best_band in eligible_bands
        ):

            if cooldown_remaining > 0:

                decision_reason = (
                    f"Current band {current_band} "
                    f"is not currently eligible, but "
                    f"cooldown blocks switching for "
                    f"{cooldown_remaining:.1f}s."
                )

            elif improvement >= switch_threshold:

                changed = True

                decision_reason = (
                    f"Switch recommended: "
                    f"{current_band} -> {best_band}. "
                    f"Improvement "
                    f"{improvement:.2f} >= "
                    f"{switch_threshold:.2f}."
                )

            else:

                decision_reason = (
                    f"Current band {current_band} "
                    f"is not preferred, but improvement "
                    f"{improvement:.2f} is below "
                    f"switch threshold "
                    f"{switch_threshold:.2f}."
                )

        # ==============================================================
        # CASE 3: Already best
        # ==============================================================

        elif best_band == current_band:

            decision_reason = (
                f"{current_band} is already the best "
                f"eligible band."
            )

        # ==============================================================
        # CASE 4: Not enough improvement
        # ==============================================================

        elif improvement < switch_threshold:

            decision_reason = (
                f"Improvement {improvement:.2f} points "
                f"is below switch threshold "
                f"{switch_threshold:.2f}."
            )

        # ==============================================================
        # CASE 5: Cooldown
        # ==============================================================

        elif cooldown_remaining > 0:

            decision_reason = (
                f"Switch blocked by cooldown. "
                f"{cooldown_remaining:.1f}s remaining."
            )

        # ==============================================================
        # CASE 6: Normal switch
        # ==============================================================

        else:

            changed = True

            decision_reason = (
                f"Switch recommended: "
                f"{current_band} -> {best_band}. "
                f"Improvement "
                f"{improvement:.2f} >= "
                f"{switch_threshold:.2f}."
            )

        return {
            "mac": mac,

            "current_band": current_band,

            "target_band": best_band,

            "best_band": best_band,

            "changed": changed,

            "decision": (
                "switch"
                if changed
                else "stay"
            ),

            # EXACT scores used for steering.
            "scores": {
                band: round(
                    score,
                    2,
                )
                for band, score in scores.items()
            },

            "current_score": round(
                current_score,
                2,
            ),

            "best_score": round(
                best_score,
                2,
            ),

            "improvement": round(
                improvement,
                2,
            ),

            "weights": weights,

            "eligible_bands": (
                eligible_bands
            ),

            "rejection_reasons": (
                rejection_reasons
            ),

            "switch_threshold": (
                switch_threshold
            ),

            "cooldown": cooldown,

            "cooldown_remaining": round(
                cooldown_remaining,
                2,
            ),

            "preferred_band": (
                rule.get(
                    "preferred_band",
                    "5G",
                )
            ),

            "device_type": (
                rule.get(
                    "device_type",
                    "Unknown",
                )
            ),

            "priority": (
                rule.get(
                    "priority",
                    "medium",
                )
            ),

            "requirements": {
                "thresholds": rule.get(
                    "thresholds",
                    {},
                ),

                "min_throughput_mbps": (
                    rule.get(
                        "min_throughput_mbps",
                        0,
                    )
                ),

                "max_airtime_percent": (
                    rule.get(
                        "max_airtime_percent",
                        80,
                    )
                ),

                "bands": rule.get(
                    "bands",
                    {},
                ),
            },

            "reasons": {
                "decision": decision_reason,
                **rejection_reasons,
            },
        }


# ============================================================================
# MAIN CONTROLLER
# ============================================================================


class MultiMetricSingleAPController:

    def __init__(
        self,
        config,
    ):

        self.config = config

        self.device_controller = (
            DeviceBandController(
                config
            )
        )

        # Actual steering timestamps.
        self.last_steering: dict[
            str,
            float,
        ] = {}

        # Dashboard state.
        self.last_steering_state: dict[
            str,
            Any,
        ] = {
            "timestamp": time.time(),
            "status": "idle",
            "devices": [],
        }

        self.last_skip_reason = (
            "No station requires steering."
        )

        # Radio byte counters.
        #
        # key:
        #     (ap_id, interface)
        #
        # value:
        #     (rx_bytes, tx_bytes, monotonic_time)
        self._previous_bytes: dict[
            tuple[str, str],
            tuple[int, int, float],
        ] = {}

        # Station byte counters.
        #
        # key:
        #     (mac, interface)
        #
        # value:
        #     (rx_bytes, tx_bytes, monotonic_time)
        self._previous_station_bytes: dict[
            tuple[str, str],
            tuple[int, int, float],
        ] = {}

        # --------------------------------------------------------------
        # BPI SSH configuration
        # --------------------------------------------------------------

        self.bpi_ssh_host = str(
            getattr(
                config,
                "bpi_ssh_host",
                os.getenv(
                    "BPI_SSH_HOST",
                    DEFAULT_BPI_HOST,
                ),
            )
            or DEFAULT_BPI_HOST
        )

        self.bpi_ssh_user = str(
            getattr(
                config,
                "bpi_ssh_user",
                os.getenv(
                    "BPI_SSH_USER",
                    DEFAULT_BPI_USER,
                ),
            )
            or DEFAULT_BPI_USER
        )

        self.bpi_ssh_port = str(
            getattr(
                config,
                "bpi_ssh_port",
                os.getenv(
                    "BPI_SSH_PORT",
                    str(DEFAULT_BPI_PORT),
                ),
            )
            or DEFAULT_BPI_PORT
        )

        self.bpi_ssh_key = str(
            getattr(
                config,
                "bpi_ssh_key",
                os.getenv(
                    "BPI_SSH_KEY",
                    "",
                ),
            )
            or ""
        )

    # ==================================================================
    # BPI SSH
    # ==================================================================

    def _ssh_bpi(
        self,
        command: str,
        timeout: float = 8.0,
    ) -> str | None:

        target = (
            f"{self.bpi_ssh_user}@"
            f"{self.bpi_ssh_host}"
        )

        args = [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            "ConnectTimeout=3",
            "-p",
            str(self.bpi_ssh_port),
        ]

        if self.bpi_ssh_key:

            args.extend(
                [
                    "-i",
                    self.bpi_ssh_key,
                ]
            )

        args.extend(
            [
                target,
                command,
            ]
        )

        try:

            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )

        except (
            subprocess.TimeoutExpired,
            OSError,
        ):

            return None

        if result.returncode != 0:

            return None

        return result.stdout

    # ==================================================================
    # HOSTAPD ALL_STA PARSER
    # ==================================================================

    def _parse_hostapd_all_sta(
        self,
        interface_name: str,
        output: str,
    ) -> list[dict[str, Any]]:

        stations: list[
            dict[str, Any]
        ] = []

        current: dict[
            str,
            Any,
        ] | None = None

        for raw_line in output.splitlines():

            line = raw_line.strip()

            if not line:
                continue

            # MAC address starts a station block.
            if re.fullmatch(
                r"[0-9a-fA-F]{2}"
                r"(?::[0-9a-fA-F]{2}){5}",
                line,
            ):

                if current is not None:

                    stations.append(
                        current
                    )

                current = {
                    "mac": _normalize_mac(
                        line
                    ),

                    "interface": (
                        interface_name
                    ),

                    "band": (
                        _band_from_interface(
                            interface_name
                        )
                    ),
                }

                continue

            if current is None:
                continue

            if "=" not in line:
                continue

            key, value = line.split(
                "=",
                1,
            )

            current[
                key.strip()
            ] = value.strip()

        if current is not None:

            stations.append(
                current
            )

        # --------------------------------------------------------------
        # Normalize important fields.
        # --------------------------------------------------------------

        for station in stations:

            signal_raw = station.get(
                "signal"
            )

            if signal_raw is None:

                station["signal"] = None
                station["rssi"] = None
                station["signal_known"] = False

            else:

                station["signal"] = (
                    _safe_float(
                        signal_raw,
                        -100,
                    )
                )

                station["rssi"] = (
                    station["signal"]
                )

                station["signal_known"] = True

            station["rx_bytes"] = max(
                0,
                _safe_int(
                    station.get(
                        "rx_bytes",
                        0,
                    )
                ),
            )

            station["tx_bytes"] = max(
                0,
                _safe_int(
                    station.get(
                        "tx_bytes",
                        0,
                    )
                ),
            )

            station[
                "rx_bitrate_mbps"
            ] = self._parse_bitrate(
                station.get(
                    "rx_bitrate",
                    0,
                )
            )

            station[
                "tx_bitrate_mbps"
            ] = self._parse_bitrate(
                station.get(
                    "tx_bitrate",
                    0,
                )
            )

            # PHY bitrate is NOT the same thing as actual throughput.
            #
            # We keep it as fallback only.
            station[
                "phy_bitrate_mbps"
            ] = max(
                station[
                    "rx_bitrate_mbps"
                ],
                station[
                    "tx_bitrate_mbps"
                ],
            )

            station[
                "throughput_mbps"
            ] = 0.0

            station[
                "throughput_known"
            ] = False

        return stations

    # ==================================================================
    # BITRATE PARSER
    # ==================================================================

    def _parse_bitrate(
        self,
        value: Any,
    ) -> float:

        if value is None:
            return 0.0

        text = str(
            value
        ).strip()

        if not text:
            return 0.0

        match = re.search(
            r"([-+]?\d+(?:\.\d+)?)",
            text,
        )

        if not match:
            return 0.0

        number = _safe_float(
            match.group(1),
            0,
        )

        lower = text.lower()

        if "kbit" in lower:
            return number / 1000.0

        if "mbit" in lower:
            return number

        if "gbit" in lower:
            return number * 1000.0

        # hostapd often reports numeric bitrate in bit/s.
        if number > 10000:
            return number / 1_000_000.0

        return number

    # ==================================================================
    # COLLECT ALL BPI STATIONS
    # ==================================================================

    def _collect_bpi_stations(
        self,
    ) -> dict[str, dict[str, Any]]:

        command = (
            "for IF in "
            "phy0.0-ap0 "
            "phy0.1-ap0 "
            "phy0.2-ap0; "
            "do "
            "echo \"__IFACE__=$IF\"; "
            "/usr/sbin/hostapd_cli "
            "-i \"$IF\" "
            "all_sta "
            "2>/dev/null; "
            "done"
        )

        output = self._ssh_bpi(
            command,
            timeout=8.0,
        )

        if output is None:
            return {}

        stations: dict[
            str,
            dict[str, Any],
        ] = {}

        chunks = output.split(
            "__IFACE__="
        )

        for chunk in chunks:

            chunk = chunk.strip()

            if not chunk:
                continue

            lines = chunk.splitlines()

            if not lines:
                continue

            current_interface = (
                lines[0].strip()
            )

            if not _is_wifi_interface(
                current_interface
            ):
                continue

            station_output = "\n".join(
                lines[1:]
            )

            parsed = (
                self._parse_hostapd_all_sta(
                    current_interface,
                    station_output,
                )
            )

            for station in parsed:

                mac = _normalize_mac(
                    station.get(
                        "mac",
                        "",
                    )
                )

                if not mac:
                    continue

                stations[mac] = station

        return stations

    # ==================================================================
    # ENRICH SNAPSHOT WITH BPI STATIONS
    # ==================================================================

    def _inject_bpi_stations(
        self,
        snapshot: dict[str, Any],
        stations: dict[str, dict[str, Any]],
    ) -> None:

        radios = snapshot.get(
            "radios",
            [],
        )

        by_interface: dict[
            str,
            list[dict[str, Any]],
        ] = {
            interface: []
            for interface in WIFI_INTERFACES
        }

        for station in stations.values():

            interface = str(
                station.get(
                    "interface",
                    "",
                )
                or ""
            )

            if interface not in by_interface:
                continue

            by_interface[
                interface
            ].append(
                station
            )

        for radio in radios:

            interface = (
                radio.interface_name
            )

            if interface not in WIFI_INTERFACES:
                continue

            bpi_clients = (
                by_interface.get(
                    interface,
                    [],
                )
            )

            radio.clients = (
                bpi_clients
            )

            # BPI is authoritative for associated stations.
            radio.client_count = len(
                bpi_clients
            )

            if not bpi_clients:

                radio.avg_signal = None

                continue

            known_signals = [
                _safe_float(
                    client.get(
                        "signal"
                    ),
                    -100,
                )
                for client in bpi_clients
                if client.get(
                    "signal"
                ) is not None
            ]

            if known_signals:

                radio.avg_signal = (
                    sum(
                        known_signals
                    )
                    / len(
                        known_signals
                    )
                )

            else:

                radio.avg_signal = None

            radio.rx_bytes = sum(
                max(
                    0,
                    _safe_int(
                        item.get(
                            "rx_bytes",
                            0,
                        )
                    ),
                )
                for item in bpi_clients
            )

            radio.tx_bytes = sum(
                max(
                    0,
                    _safe_int(
                        item.get(
                            "tx_bytes",
                            0,
                        )
                    ),
                )
                for item in bpi_clients
            )

    # ==================================================================
    # RADIO SCORE
    # ==================================================================

    def _calculate_radio_score(
        self,
        radio: RadioState,
        radios: list[RadioState],
    ) -> float:
        """
        Diagnostic radio score only.

        IMPORTANT:
        This score is NOT used for station steering.

        Station steering uses:
            DeviceBandController.decide_band()
        """

        # --------------------------------------------------------------
        # RSSI
        # --------------------------------------------------------------

        if radio.avg_signal is not None:

            rssi_score = _clamp(
                (
                    radio.avg_signal
                    + 90.0
                )
                / 40.0
            )

        else:

            rssi_score = 0.5

        # --------------------------------------------------------------
        # Airtime
        # --------------------------------------------------------------

        airtime_score = _clamp(
            1.0
            - (
                float(
                    radio.total_airtime
                )
                / 100.0
            )
        )

        # --------------------------------------------------------------
        # Client load
        # --------------------------------------------------------------

        clients_values = [
            max(
                0,
                item.client_count,
            )
            for item in radios
            if item.band in VALID_BANDS
        ]

        max_clients = max(
            [
                1,
                *clients_values,
            ]
        )

        client_score = _clamp(
            1.0
            - (
                float(
                    max(
                        0,
                        radio.client_count,
                    )
                )
                / float(
                    max_clients
                )
            )
        )

        # --------------------------------------------------------------
        # Throughput
        # --------------------------------------------------------------

        throughput_values = [
            max(
                0.0,
                item.throughput_mbps,
            )
            for item in radios
            if item.band in VALID_BANDS
        ]

        max_throughput = max(
            [
                1.0,
                *throughput_values,
            ]
        )

        throughput_score = _clamp(
            radio.throughput_mbps
            / max_throughput
        )

        # --------------------------------------------------------------
        # Config weights
        # --------------------------------------------------------------

        w_rssi = _safe_float(
            getattr(
                self.config,
                "weight_rssi",
                0.25,
            ),
            0.25,
        )

        w_airtime = _safe_float(
            getattr(
                self.config,
                "weight_airtime",
                0.25,
            ),
            0.25,
        )

        w_clients = _safe_float(
            getattr(
                self.config,
                "weight_clients",
                0.20,
            ),
            0.20,
        )

        w_throughput = _safe_float(
            getattr(
                self.config,
                "weight_throughput",
                0.30,
            ),
            0.30,
        )

        total = (
            w_rssi
            + w_airtime
            + w_clients
            + w_throughput
        )

        if total <= 0:
            return 0.0

        score = (
            w_rssi
            * rssi_score

            + w_airtime
            * airtime_score

            + w_clients
            * client_score

            + w_throughput
            * throughput_score
        )

        return round(
            score / total,
            4,
        )

    # ==================================================================
    # RADIO THROUGHPUT
    # ==================================================================

    def _update_throughput(
        self,
        radio: RadioState,
    ) -> None:

        now = time.monotonic()

        key = (
            radio.ap_id,
            radio.interface_name,
        )

        current_rx = max(
            0,
            radio.rx_bytes,
        )

        current_tx = max(
            0,
            radio.tx_bytes,
        )

        previous = (
            self._previous_bytes.get(
                key
            )
        )

        if previous is None:

            self._previous_bytes[
                key
            ] = (
                current_rx,
                current_tx,
                now,
            )

            # First sample = unknown.
            radio.throughput_mbps = 0.0

            return

        (
            previous_rx,
            previous_tx,
            previous_time,
        ) = previous

        elapsed = (
            now
            - previous_time
        )

        self._previous_bytes[
            key
        ] = (
            current_rx,
            current_tx,
            now,
        )

        if elapsed <= 0:
            return

        # Counter reset handling.
        delta_rx = (
            current_rx
            - previous_rx
        )

        delta_tx = (
            current_tx
            - previous_tx
        )

        if delta_rx < 0:
            delta_rx = 0

        if delta_tx < 0:
            delta_tx = 0

        delta_bytes = (
            delta_rx
            + delta_tx
        )

        if delta_bytes <= 0:

            radio.throughput_mbps = 0.0

            return

        calculated_mbps = (
            delta_bytes
            * 8.0
            / elapsed
            / 1_000_000.0
        )

        radio.throughput_mbps = round(
            max(
                0.0,
                calculated_mbps,
            ),
            4,
        )

    # ==================================================================
    # STATION THROUGHPUT
    # ==================================================================

    def _station_throughput(
        self,
        station: dict[str, Any],
    ) -> tuple[float, bool]:

        mac = _normalize_mac(
            station.get(
                "mac",
                "",
            )
        )

        interface = str(
            station.get(
                "interface",
                "",
            )
            or ""
        )

        if not mac or not interface:

            return (
                0.0,
                False,
            )

        current_rx = max(
            0,
            _safe_int(
                station.get(
                    "rx_bytes",
                    0,
                )
            ),
        )

        current_tx = max(
            0,
            _safe_int(
                station.get(
                    "tx_bytes",
                    0,
                )
            ),
        )

        now = time.monotonic()

        key = (
            mac,
            interface,
        )

        previous = (
            self._previous_station_bytes.get(
                key
            )
        )

        # --------------------------------------------------------------
        # First observation
        # --------------------------------------------------------------

        if previous is None:

            self._previous_station_bytes[
                key
            ] = (
                current_rx,
                current_tx,
                now,
            )

            # PHY bitrate is only a fallback.
            phy_bitrate = _safe_float(
                station.get(
                    "phy_bitrate_mbps",
                    0,
                ),
                0,
            )

            if phy_bitrate > 0:

                return (
                    phy_bitrate,
                    True,
                )

            return (
                0.0,
                False,
            )

        (
            previous_rx,
            previous_tx,
            previous_time,
        ) = previous

        elapsed = (
            now
            - previous_time
        )

        self._previous_station_bytes[
            key
        ] = (
            current_rx,
            current_tx,
            now,
        )

        if elapsed <= 0:

            return (
                0.0,
                False,
            )

        delta_rx = (
            current_rx
            - previous_rx
        )

        delta_tx = (
            current_tx
            - previous_tx
        )

        # Counter reset.
        if delta_rx < 0:
            delta_rx = 0

        if delta_tx < 0:
            delta_tx = 0

        delta = (
            delta_rx
            + delta_tx
        )

        if delta > 0:

            calculated = (
                delta
                * 8.0
                / elapsed
                / 1_000_000.0
            )

            if calculated > 0:

                return (
                    round(
                        calculated,
                        4,
                    ),
                    True,
                )

        # Fallback to PHY bitrate.
        phy_bitrate = _safe_float(
            station.get(
                "phy_bitrate_mbps",
                0,
            ),
            0,
        )

        if phy_bitrate > 0:

            return (
                phy_bitrate,
                True,
            )

        return (
            0.0,
            False,
        )

    # ==================================================================
    # PREPARE SNAPSHOT
    # ==================================================================

    def _prepare_snapshot(
        self,
        snapshot: dict[str, Any],
    ) -> None:

        radios = [
            radio
            for radio in snapshot.get(
                "radios",
                [],
            )
            if radio.band in VALID_BANDS
        ]

        for radio in radios:

            self._update_throughput(
                radio
            )

        for radio in radios:

            radio.score = (
                self._calculate_radio_score(
                    radio,
                    radios,
                )
            )

    # ==================================================================
    # STATION METRICS
    # ==================================================================

    def _station_metrics(
        self,
        snapshot: dict[str, Any],
        station: str,
    ) -> dict[str, dict[str, Any]]:

        station = _normalize_mac(
            station
        )

        metrics: dict[
            str,
            dict[str, Any],
        ] = {}

        for radio in snapshot.get(
            "radios",
            [],
        ):

            if radio.band not in VALID_BANDS:
                continue

            station_data = None

            for client in (
                radio.clients
                or []
            ):

                client_mac = (
                    _extract_station_mac(
                        client
                    )
                )

                if client_mac == station:

                    station_data = client

                    break

            # ==========================================================
            # Station currently associated with this band
            # ==========================================================

            if station_data is not None:

                signal_value = (
                    station_data.get(
                        "signal"
                    )
                )

                signal_known = (
                    signal_value is not None
                )

                rssi = (
                    _safe_float(
                        signal_value,
                        -100,
                    )
                    if signal_known
                    else None
                )

                (
                    throughput,
                    throughput_known,
                ) = self._station_throughput(
                    station_data
                )

                metrics[radio.band] = {
                    "rssi": rssi,

                    "rssi_known": (
                        signal_known
                    ),

                    "airtime": (
                        _safe_float(
                            radio.total_airtime,
                            0,
                        )
                    ),

                    "airtime_known": (
                        radio.total_airtime
                        is not None
                    ),

                    "throughput_mbps": (
                        throughput
                    ),

                    "throughput_known": (
                        throughput_known
                    ),

                    "clients": _safe_int(
                        radio.client_count,
                        0,
                    ),

                    "txpower": (
                        _safe_float(
                            radio.tx_power,
                            0,
                        )
                        if radio.tx_power
                        is not None
                        else None
                    ),

                    "interface": (
                        radio.interface_name
                    ),

                    "radio": radio,

                    "station_data": (
                        station_data
                    ),

                    "associated": True,
                }

                continue

            # ==========================================================
            # Candidate band
            #
            # Station is NOT associated here.
            #
            # Therefore:
            #   RSSI = unknown
            #   client throughput = unknown
            #
            # Do not fabricate measurements.
            # ==========================================================

            metrics[radio.band] = {
                "rssi": None,

                "rssi_known": False,

                "airtime": (
                    _safe_float(
                        radio.total_airtime,
                        0,
                    )
                ),

                "airtime_known": (
                    radio.total_airtime > 0
                ),

                "throughput_mbps": (
                    _safe_float(
                        radio.throughput_mbps,
                        0,
                    )
                ),

                "throughput_known": (
                    radio.throughput_mbps > 0
                ),

                "clients": _safe_int(
                    radio.client_count,
                    0,
                ),

                "txpower": (
                    _safe_float(
                        radio.tx_power,
                        0,
                    )
                    if radio.tx_power
                    is not None
                    else None
                ),

                "interface": (
                    radio.interface_name
                ),

                "radio": radio,

                "station_data": None,

                "associated": False,
            }

        return metrics

    # ==================================================================
    # FIND STATION
    # ==================================================================

    def _find_station(
        self,
        snapshot: dict[str, Any],
    ) -> tuple[
        str | None,
        RadioState | None,
    ]:

        candidates = []

        for radio in snapshot.get(
            "radios",
            [],
        ):

            if radio.band not in VALID_BANDS:
                continue

            for client in (
                radio.clients
                or []
            ):

                mac = _extract_station_mac(
                    client
                )

                if not mac:
                    continue

                signal_value = client.get(
                    "signal"
                )

                if signal_value is None:
                    signal = -100.0
                else:
                    signal = _safe_float(
                        signal_value,
                        -100,
                    )

                candidates.append(
                    (
                        mac,
                        radio,
                        signal,
                    )
                )

        if not candidates:
            return (
                None,
                None,
            )

        # Weakest station first.
        selected = min(
            candidates,
            key=lambda item: item[2],
        )

        return (
            selected[0],
            selected[1],
        )

    # ==================================================================
    # TARGET RADIO
    # ==================================================================

    def _find_target_radio(
        self,
        snapshot: dict[str, Any],
        target_band: str,
    ) -> RadioState | None:

        target_band = str(
            target_band or ""
        ).upper()

        for radio in snapshot.get(
            "radios",
            [],
        ):

            if (
                radio.band.upper()
                == target_band
            ):
                return radio

        return None

    # ==================================================================
    # TARGET BSSID
    # ==================================================================

    def _get_radio_bssid(
        self,
        radio: RadioState,
    ) -> str | None:

        raw = (
            radio.raw
            if isinstance(
                radio.raw,
                dict,
            )
            else {}
        )

        value = (
            raw.get("bssid")
            or raw.get("BSSID")
            or raw.get("bssid_address")
            or raw.get("radio_bssid")
            or raw.get("hwaddr")
            or raw.get("mac")
        )

        if value is None:
            return None

        value = str(
            value
        ).strip()

        if not value:
            return None

        return _normalize_mac(
            value
        )

    # ==================================================================
    # BSS TRANSITION COMMAND
    # ==================================================================

    def _build_bss_tm_command(
        self,
        source_interface: str,
        station: str,
        target_bssid: str | None,
    ) -> str:

        command = (
            "/usr/sbin/hostapd_cli "
            f"-i {shlex.quote(source_interface)} "
            "bss_tm_req "
            f"{shlex.quote(station)}"
        )

        if target_bssid:

            command += (
                " pref="
                + shlex.quote(
                    target_bssid
                )
            )

        return command

    # ==================================================================
    # STEERING STATE
    # ==================================================================

    def _build_device_state(
        self,
        station: str,
        metrics: dict[str, dict[str, Any]],
        decision: dict[str, Any],
    ) -> dict[str, Any]:

        ui_metrics = {}

        for band, value in metrics.items():

            ui_metrics[band] = {
                "rssi": (
                    _safe_float(
                        value.get(
                            "rssi"
                        ),
                        -100,
                    )
                    if value.get(
                        "rssi"
                    ) is not None
                    else None
                ),

                "rssi_known": bool(
                    value.get(
                        "rssi_known",
                        False,
                    )
                ),

                "throughput_mbps": (
                    _safe_float(
                        value.get(
                            "throughput_mbps",
                            0,
                        ),
                        0,
                    )
                ),

                "throughput_known": bool(
                    value.get(
                        "throughput_known",
                        False,
                    )
                ),

                "airtime": _safe_float(
                    value.get(
                        "airtime",
                        0,
                    ),
                    0,
                ),

                "airtime_known": bool(
                    value.get(
                        "airtime_known",
                        False,
                    )
                ),

                "clients": _safe_int(
                    value.get(
                        "clients",
                        0,
                    ),
                    0,
                ),

                "txpower": (
                    _safe_float(
                        value.get(
                            "txpower"
                        ),
                        0,
                    )
                    if value.get(
                        "txpower"
                    ) is not None
                    else None
                ),

                "interface": value.get(
                    "interface",
                    "",
                ),

                "associated": bool(
                    value.get(
                        "associated",
                        False,
                    )
                ),
            }

        return {
            "mac": station,

            "hostname": station,

            "current_band": decision.get(
                "current_band",
                "",
            ),

            "best_band": decision.get(
                "best_band",
                "",
            ),

            "target_band": decision.get(
                "target_band",
                "",
            ),

            "scores": decision.get(
                "scores",
                {},
            ),

            "metrics": ui_metrics,

            "weights": decision.get(
                "weights",
                {},
            ),

            "eligible_bands": decision.get(
                "eligible_bands",
                [],
            ),

            "reasons": decision.get(
                "reasons",
                {},
            ),

            "rejection_reasons": decision.get(
                "rejection_reasons",
                {},
            ),

            "switch_threshold": decision.get(
                "switch_threshold",
                0,
            ),

            "cooldown": decision.get(
                "cooldown",
                0,
            ),

            "cooldown_remaining": decision.get(
                "cooldown_remaining",
                0,
            ),

            "improvement": decision.get(
                "improvement",
                0,
            ),

            "decision": decision.get(
                "decision",
                "stay",
            ),

            "switched": False,

            "preferred_band": decision.get(
                "preferred_band",
                "",
            ),

            "device_type": decision.get(
                "device_type",
                "Unknown",
            ),

            "priority": decision.get(
                "priority",
                "medium",
            ),

            "requirements": decision.get(
                "requirements",
                {},
            ),
        }

    # ==================================================================
    # MAIN DECISION
    # ==================================================================

    def decide(
        self,
        snapshots: dict[
            str,
            dict[str, Any],
        ],
    ) -> ControlAction | None:

        self.last_skip_reason = (
            "No station requires steering."
        )

        if not snapshots:

            self.last_steering_state = {
                "timestamp": time.time(),
                "status": "no_snapshot",
                "devices": [],
            }

            self.last_skip_reason = (
                "No monitoring snapshot."
            )

            return None

        # --------------------------------------------------------------
        # Single AP architecture.
        # --------------------------------------------------------------

        snapshot = next(
            iter(
                snapshots.values()
            )
        )

        # --------------------------------------------------------------
        # BPI station collection.
        #
        # IMPORTANT:
        # Collect once per decision cycle, not once per AP.
        # --------------------------------------------------------------

        bpi_stations = (
            self._collect_bpi_stations()
        )

        self._inject_bpi_stations(
            snapshot,
            bpi_stations,
        )

        self._prepare_snapshot(
            snapshot
        )

        # --------------------------------------------------------------
        # Find station.
        # --------------------------------------------------------------

        station, current_radio = (
            self._find_station(
                snapshot
            )
        )

        if not station:

            self.last_steering_state = {
                "timestamp": time.time(),
                "status": "idle",
                "devices": [],
            }

            self.last_skip_reason = (
                "No station found on BPI-R4."
            )

            return None

        if current_radio is None:

            self.last_skip_reason = (
                "Current radio not found."
            )

            return None

        current_band = (
            current_radio.band
            or _band_from_interface(
                current_radio.interface_name
            )
        )

        current_band = str(
            current_band
        ).upper()

        # --------------------------------------------------------------
        # SSID filter.
        # --------------------------------------------------------------

        target_ssid = str(
            getattr(
                self.config,
                "target_ssid",
                "",
            )
            or ""
        )

        if (
            target_ssid
            and current_radio.ssid
            and current_radio.ssid
            != target_ssid
        ):

            self.last_skip_reason = (
                f"Station {station} is on SSID "
                f"{current_radio.ssid}, "
                f"not target SSID "
                f"{target_ssid}."
            )

            return None

        # --------------------------------------------------------------
        # Station metrics.
        # --------------------------------------------------------------

        metrics = self._station_metrics(
            snapshot,
            station,
        )

        if not metrics:

            self.last_skip_reason = (
                f"No band metrics available "
                f"for station {station}."
            )

            return None

        # --------------------------------------------------------------
        # Optimization decision.
        # --------------------------------------------------------------

        decision = (
            self.device_controller.decide_band(
                station,
                current_band,
                metrics,
            )
        )

        # --------------------------------------------------------------
        # Dashboard state.
        # --------------------------------------------------------------

        device_state = (
            self._build_device_state(
                station,
                metrics,
                decision,
            )
        )

        self.last_steering_state = {
            "timestamp": time.time(),

            "status": (
                "switch"
                if decision.get(
                    "changed",
                    False,
                )
                else "idle"
            ),

            "devices": [
                device_state
            ],
        }

        # --------------------------------------------------------------
        # No switch.
        # --------------------------------------------------------------

        if not decision.get(
            "changed",
            False,
        ):

            self.last_skip_reason = (
                decision.get(
                    "reasons",
                    {},
                ).get(
                    "decision",
                    "Current band is already optimal.",
                )
            )

            return None

        # --------------------------------------------------------------
        # Target band.
        # --------------------------------------------------------------

        target_band = str(
            decision.get(
                "target_band",
                "",
            )
            or ""
        ).upper()

        if not target_band:

            self.last_skip_reason = (
                "No target band selected."
            )

            self.last_steering_state[
                "status"
            ] = "error"

            self.last_steering_state[
                "devices"
            ][0][
                "decision"
            ] = "error"

            self.last_steering_state[
                "devices"
            ][0].setdefault(
                "reasons",
                {},
            )[
                "decision"
            ] = (
                "No target band selected."
            )

            return None

        # --------------------------------------------------------------
        # Target radio.
        # --------------------------------------------------------------

        target_radio = (
            self._find_target_radio(
                snapshot,
                target_band,
            )
        )

        if target_radio is None:

            self.last_skip_reason = (
                f"Target radio {target_band} "
                "not available."
            )

            self.last_steering_state[
                "status"
            ] = "error"

            self.last_steering_state[
                "devices"
            ][0][
                "decision"
            ] = "error"

            self.last_steering_state[
                "devices"
            ][0].setdefault(
                "reasons",
                {},
            )[
                "decision"
            ] = (
                f"Target radio {target_band} "
                "not available."
            )

            return None

        target_interface = (
            target_radio.interface_name
        )

        target_bssid = (
            self._get_radio_bssid(
                target_radio
            )
        )

        # --------------------------------------------------------------
        # IMPORTANT:
        # Use exactly the decision scores.
        # --------------------------------------------------------------

        current_score = _safe_float(
            decision.get(
                "scores",
                {},
            ).get(
                current_band,
                0,
            ),
            0,
        )

        target_score = _safe_float(
            decision.get(
                "scores",
                {},
            ).get(
                target_band,
                0,
            ),
            0,
        )

        improvement = (
            target_score
            - current_score
        )

        reason = decision.get(
            "reasons",
            {},
        ).get(
            "decision",
            (
                f"{current_band} -> "
                f"{target_band}"
            ),
        )

        # --------------------------------------------------------------
        # Build BSS transition request.
        # --------------------------------------------------------------

        command = (
            self._build_bss_tm_command(
                source_interface=(
                    current_radio.interface_name
                ),
                station=station,
                target_bssid=target_bssid,
            )
        )

        return ControlAction(
            ap=APState(
                name=snapshot.get(
                    "ap_name",
                    getattr(
                        self.config.ap,
                        "name",
                        "",
                    ),
                ),

                device_id=snapshot.get(
                    "ap_id",
                    getattr(
                        self.config.ap,
                        "device_id",
                        "",
                    ),
                ),

                control_device_id=getattr(
                    self.config.ap,
                    "control_device_id",
                    "",
                ),

                radios=(
                    getattr(
                        self.config.ap,
                        "radios",
                        (),
                    )
                ),
            ),

            station=station,

            interface_name=(
                current_radio.interface_name
            ),

            band=current_band,

            source_band=current_band,

            target_band=target_band,

            target_interface=target_interface,

            target_bssid=target_bssid,

            score_current=current_score,

            score_target=target_score,

            improvement=improvement,

            action_type=(
                "station_band_steering"
            ),

            old_value=None,

            new_value=None,

            reason=reason,

            command=command,
        )

    # ==================================================================
    # REGISTER STEERING
    # ==================================================================

    def register_steering(
        self,
        action: ControlAction,
    ) -> None:

        if not action.station:
            return

        mac = _normalize_mac(
            action.station
        )

        now = time.monotonic()

        # --------------------------------------------------------------
        # Keep both cooldown stores synchronized.
        # --------------------------------------------------------------

        self.last_steering[
            mac
        ] = now

        self.device_controller._last_switch[
            mac
        ] = now

        # --------------------------------------------------------------
        # Update dashboard state.
        # --------------------------------------------------------------

        devices = (
            self.last_steering_state.get(
                "devices"
            )
        )

        if devices:

            device = devices[0]

            device["decision"] = (
                "switch"
            )

            device["switched"] = True

            device["switch_timestamp"] = (
                time.time()
            )

            device["source_band"] = (
                action.source_band
            )

            device["target_band"] = (
                action.target_band
            )

            device["target_interface"] = (
                action.target_interface
            )

            device["target_bssid"] = (
                action.target_bssid
            )

            device["score_current"] = (
                action.score_current
            )

            device["score_target"] = (
                action.score_target
            )

            device["improvement"] = (
                action.improvement
            )

            device["action_type"] = (
                action.action_type
            )

            device["command"] = (
                action.command
            )

            device["reason"] = (
                action.reason
            )

        self.last_steering_state[
            "timestamp"
        ] = time.time()

        self.last_steering_state[
            "status"
        ] = "switch"

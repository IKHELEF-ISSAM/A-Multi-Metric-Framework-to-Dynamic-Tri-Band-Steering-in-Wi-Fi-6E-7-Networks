from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = ROOT_DIR / ".env"


def load_dotenv(path: Path = DEFAULT_ENV_PATH) -> None:
    """Load .env values without overwriting existing environment variables."""
    if not path.exists():
        return

    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        os.environ.setdefault(
            key.strip(),
            value.strip().strip('"').strip("'"),
        )


@dataclass(frozen=True)
class RadioConfig:
    band: str
    interface_name: str
    uci_radio: str


@dataclass(frozen=True)
class APConfig:
    name: str
    device_id: str
    device_key: str
    control_device_id: str
    radios: tuple[RadioConfig, ...]


@dataclass(frozen=True)
class AppConfig:
    bpi_ssh_host: str
    bpi_ssh_user: str
    bpi_ssh_port: int
    bpi_ssh_key: str
    bpi_ssh_timeout: float
    bpi_allow_changes: bool

    # SQLite database used for telemetry/control history.
    db_path: Path

    # JSON file used as the source of truth for per-device rules.
    device_rules_path: Path

    poll_interval: float

    target_ssid: str

    txpower_step: int
    min_txpower: int
    max_txpower: int

    client_diff_threshold: int
    control_cooldown: int

    # Global/default score weights.
    weight_clients: float
    weight_rssi: float
    weight_airtime: float
    weight_throughput: float
    weight_txpower: float

    # Default band thresholds.
    default_min_rssi_2g: float
    default_min_rssi_5g: float
    default_min_rssi_6g: float

    default_min_throughput_mbps: float
    default_max_airtime_percent: float

    default_switch_threshold: float
    default_rule_cooldown: int

    ap: APConfig


def _get_required(name: str) -> str:
    value = os.getenv(name)

    if value is None or value == "":
        raise ValueError(
            f"Missing required environment variable: {name}"
        )

    return value


def _get_optional(name: str, default: str) -> str:
    return os.getenv(name, default)


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _get_int(name: str, default: int) -> int:
    value = os.getenv(name)

    if value is None or value == "":
        return default

    return int(value)


def _get_float(name: str, default: float) -> float:
    value = os.getenv(name)

    if value is None or value == "":
        return default

    return float(value)


def _load_ap(prefix: str) -> APConfig:
    device_id = _get_optional(f"{prefix}_DEVICE_ID", prefix)

    radios = []

    for band in ("2G", "5G", "6G"):
        iface = os.getenv(
            f"{prefix}_RADIO_{band}_IFACE",
            "",
        ).strip()

        uci = os.getenv(
            f"{prefix}_RADIO_{band}_UCI",
            "",
        ).strip()

        if iface and uci:
            radios.append(
                RadioConfig(
                    band=band,
                    interface_name=iface,
                    uci_radio=uci,
                )
            )

    if not radios:
        raise ValueError(
            f"No radios configured for {prefix}."
        )

    return APConfig(
        name=_get_optional(
            f"{prefix}_NAME",
            prefix,
        ),
        device_id=device_id,
        device_key="",
        control_device_id=_get_optional(
            f"{prefix}_CONTROL_DEVICE_ID",
            device_id,
        ),
        radios=tuple(radios),
    )


def load_config() -> AppConfig:
    load_dotenv()

    return AppConfig(
        bpi_ssh_host=_get_required("BPI_SSH_HOST"),
        bpi_ssh_user=_get_optional("BPI_SSH_USER", "root"),
        bpi_ssh_port=_get_int("BPI_SSH_PORT", 22),
        bpi_ssh_key=_get_optional("BPI_SSH_KEY", ""),
        bpi_ssh_timeout=_get_float("BPI_SSH_TIMEOUT", 15.0),
        bpi_allow_changes=_get_bool("BPI_ALLOW_CHANGES", False),

        # SQLite database used for telemetry/control history.
        db_path=Path(
            _get_optional(
                "OPENWRT_DB_PATH",
                str(ROOT_DIR / "rssi_lb.sqlite3"),
            )
        ),

        # JSON file used for per-device steering rules.
        #
        # Default:
        # <repository>/device_rules.json
        device_rules_path=Path(
            _get_optional(
                "OPENWRT_DEVICE_RULES_PATH",
                str(ROOT_DIR / "device_rules.json"),
            )
        ),

        poll_interval=_get_float(
            "OPENWRT_POLL_INTERVAL",
            5.0,
        ),

        target_ssid=_get_optional(
            "OPENWRT_TARGET_SSID",
            "",
        ),

        txpower_step=_get_int(
            "OPENWRT_TXPOWER_STEP",
            3,
        ),

        min_txpower=_get_int(
            "OPENWRT_MIN_TXPOWER",
            8,
        ),

        max_txpower=_get_int(
            "OPENWRT_MAX_TXPOWER",
            23,
        ),

        client_diff_threshold=_get_int(
            "OPENWRT_CLIENT_DIFF_THRESHOLD",
            2,
        ),

        control_cooldown=_get_int(
            "OPENWRT_CONTROL_COOLDOWN",
            60,
        ),

        # Existing global/default weights.
        weight_clients=_get_float(
            "OPENWRT_WEIGHT_CLIENTS",
            0.30,
        ),

        weight_rssi=_get_float(
            "OPENWRT_WEIGHT_RSSI",
            0.20,
        ),

        weight_airtime=_get_float(
            "OPENWRT_WEIGHT_AIRTIME",
            0.25,
        ),

        weight_throughput=_get_float(
            "OPENWRT_WEIGHT_THROUGHPUT",
            0.15,
        ),

        weight_txpower=_get_float(
            "OPENWRT_WEIGHT_TXPOWER",
            0.10,
        ),

        # Defaults used when a device has no custom rule.
        default_min_rssi_2g=_get_float(
            "OPENWRT_DEFAULT_MIN_RSSI_2G",
            -75.0,
        ),

        default_min_rssi_5g=_get_float(
            "OPENWRT_DEFAULT_MIN_RSSI_5G",
            -70.0,
        ),

        default_min_rssi_6g=_get_float(
            "OPENWRT_DEFAULT_MIN_RSSI_6G",
            -65.0,
        ),

        default_min_throughput_mbps=_get_float(
            "OPENWRT_DEFAULT_MIN_THROUGHPUT_MBPS",
            5.0,
        ),

        default_max_airtime_percent=_get_float(
            "OPENWRT_DEFAULT_MAX_AIRTIME_PERCENT",
            80.0,
        ),

        default_switch_threshold=_get_float(
            "OPENWRT_DEFAULT_SWITCH_THRESHOLD",
            1.0,
        ),

        default_rule_cooldown=_get_int(
            "OPENWRT_DEFAULT_RULE_COOLDOWN",
            60,
        ),

        ap=_load_ap("AP1"),
    )
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


BANDS = ("2G", "5G", "6G")


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
        "2G": {"min_rssi": -75.0},
        "5G": {"min_rssi": -70.0},
        "6G": {"min_rssi": -65.0},
    },
    "min_throughput_mbps": 5.0,
    "max_airtime_percent": 80.0,
    "switch_threshold": 10.0,
    "cooldown": 180,
}


def _normalize_mac(mac: str) -> str:
    return str(mac or "").strip().lower().replace("-", ":")


def _deep_copy_rule(rule: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(rule))


def _merge_defaults(rule: dict[str, Any] | None) -> dict[str, Any]:
    result = _deep_copy_rule(DEFAULT_RULE)

    if not isinstance(rule, dict):
        return result

    for key, value in rule.items():
        if key in {"bands", "weights", "thresholds"} and isinstance(value, dict):
            if key == "thresholds":
                for band in BANDS:
                    if isinstance(value.get(band), dict):
                        result["thresholds"][band].update(value[band])
            else:
                result[key].update(value)
        else:
            result[key] = value

    return result


class DeviceRuleStore:
    """
    Persistent per-device rules stored in a JSON file.

    The JSON structure is:

    {
        "02:00:00:00:00:02": {
            ...
        }
    }
    """

    def __init__(self, rules_path: str | Path):
        self.rules_path = Path(rules_path)

        self.rules_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._ensure_file()

        print(
            f"[DEVICE-RULES] Using JSON file: {self.rules_path}"
        )

    def _ensure_file(self) -> None:
        if not self.rules_path.exists():
            self._write_all({})

    def _read_all(self) -> dict[str, dict[str, Any]]:
        if not self.rules_path.exists():
            return {}

        try:
            with self.rules_path.open(
                "r",
                encoding="utf-8",
            ) as f:
                data = json.load(f)
        except (
            OSError,
            json.JSONDecodeError,
            TypeError,
        ):
            print(
                f"[DEVICE-RULES] Warning: unable to read "
                f"{self.rules_path}; using empty rules."
            )
            return {}

        if not isinstance(data, dict):
            print(
                f"[DEVICE-RULES] Warning: invalid root object in "
                f"{self.rules_path}; using empty rules."
            )
            return {}

        result: dict[str, dict[str, Any]] = {}

        for mac, rule in data.items():
            normalized_mac = _normalize_mac(mac)

            if not isinstance(rule, dict):
                continue

            result[normalized_mac] = _merge_defaults(rule)

        return result

    def _write_all(
        self,
        rules: dict[str, dict[str, Any]],
    ) -> None:
        self.rules_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Atomic write:
        # write to a temporary file, then replace the real file.
        fd, temp_path = tempfile.mkstemp(
            prefix=".device_rules_",
            suffix=".tmp",
            dir=str(self.rules_path.parent),
        )

        try:
            with os.fdopen(
                fd,
                "w",
                encoding="utf-8",
            ) as f:
                json.dump(
                    rules,
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
                f.write("\n")
                f.flush()
                os.fsync(f.fileno())

            os.replace(
                temp_path,
                self.rules_path,
            )

        except Exception:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

            raise

    def get(self, mac: str) -> dict[str, Any]:
        mac = _normalize_mac(mac)

        rules = self._read_all()

        stored = rules.get(mac)

        if stored is None:
            print(
                f"[DEVICE-RULES] MAC={mac} -> no stored rule, "
                f"using defaults"
            )

            return _deep_copy_rule(DEFAULT_RULE)

        rule = _merge_defaults(stored)

        print(
            f"[DEVICE-RULES] MAC={mac} -> "
            f"preferred_band={rule.get('preferred_band')}"
        )

        return rule

    def get_all(self) -> dict[str, dict[str, Any]]:
        rules = self._read_all()

        result: dict[str, dict[str, Any]] = {}

        for mac, rule in rules.items():
            result[_normalize_mac(mac)] = _merge_defaults(rule)

        return result

    def save(
        self,
        mac: str,
        rule: dict[str, Any],
    ) -> dict[str, Any]:
        mac = _normalize_mac(mac)

        merged = _merge_defaults(rule)

        self._validate(
            mac,
            merged,
        )

        rules = self._read_all()

        rules[mac] = merged

        self._write_all(rules)

        print(
            f"[DEVICE-RULES] Saved MAC={mac} "
            f"preferred_band={merged.get('preferred_band')}"
        )

        return _deep_copy_rule(merged)

    def delete(self, mac: str) -> None:
        mac = _normalize_mac(mac)

        rules = self._read_all()

        if mac in rules:
            del rules[mac]
            self._write_all(rules)

            print(
                f"[DEVICE-RULES] Deleted MAC={mac}"
            )

    @staticmethod
    def _validate(
        mac: str,
        rule: dict[str, Any],
    ) -> None:
        parts = mac.split(":")

        if (
            len(parts) != 6
            or any(
                len(p) != 2
                for p in parts
            )
        ):
            raise ValueError(
                f"Invalid MAC address: {mac}"
            )

        weights = rule["weights"]

        total = sum(
            float(weights.get(k, 0))
            for k in weights
        )

        if total <= 0:
            raise ValueError(
                "At least one score weight must be > 0."
            )

        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"Score weights must sum to 1.0; "
                f"got {total:.4f}"
            )

        enabled = [
            band
            for band in BANDS
            if rule["bands"].get(band, False)
        ]

        if not enabled:
            raise ValueError(
                "At least one Wi-Fi band must be enabled."
            )

        preferred_band = str(
            rule.get("preferred_band", "")
        ).upper()

        if preferred_band not in enabled:
            raise ValueError(
                "preferred_band must be one of the enabled bands."
            )

        for band in BANDS:
            threshold = float(
                rule["thresholds"][band]["min_rssi"]
            )

            if threshold > -20 or threshold < -100:
                raise ValueError(
                    f"Invalid minimum RSSI for {band}: "
                    f"{threshold}"
                )

        if float(
            rule["min_throughput_mbps"]
        ) < 0:
            raise ValueError(
                "min_throughput_mbps cannot be negative."
            )

        if not 0 <= float(
            rule["max_airtime_percent"]
        ) <= 100:
            raise ValueError(
                "max_airtime_percent must be between 0 and 100."
            )

        if float(
            rule["switch_threshold"]
        ) < 0:
            raise ValueError(
                "switch_threshold cannot be negative."
            )

        if int(
            rule["cooldown"]
        ) < 0:
            raise ValueError(
                "cooldown cannot be negative."
            )
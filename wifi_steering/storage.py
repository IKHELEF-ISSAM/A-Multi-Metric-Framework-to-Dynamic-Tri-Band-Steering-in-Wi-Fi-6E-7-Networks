"""
SQLite persistence layer for the BPI-R4 experiment.
"""

from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path
from typing import Any

from .controller import (
    ControlAction,
    RadioState,
)


SCHEMA = """

CREATE TABLE IF NOT EXISTS poll_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    timestamp TEXT NOT NULL,

    ap_id TEXT NOT NULL,
    ap_name TEXT NOT NULL,

    raw_json TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS radio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    snapshot_id INTEGER NOT NULL,

    interface_name TEXT NOT NULL,

    band TEXT,

    ssid TEXT,

    channel INTEGER,

    frequency INTEGER,

    tx_power INTEGER,

    noise INTEGER,

    htmode TEXT,

    up INTEGER NOT NULL,

    client_count INTEGER NOT NULL,

    avg_signal REAL,

    total_airtime INTEGER NOT NULL,

    rx_bytes INTEGER NOT NULL,

    tx_bytes INTEGER NOT NULL,

    rx_packets INTEGER NOT NULL,

    tx_packets INTEGER NOT NULL,

    raw_json TEXT NOT NULL,

    FOREIGN KEY(snapshot_id)
        REFERENCES poll_snapshots(id)
);


CREATE TABLE IF NOT EXISTS station_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    radio_snapshot_id INTEGER NOT NULL,

    station_mac TEXT NOT NULL,

    vendor TEXT,

    signal INTEGER,

    rx_rate INTEGER,

    tx_rate INTEGER,

    rx_bytes INTEGER,

    tx_bytes INTEGER,

    rx_packets INTEGER,

    tx_packets INTEGER,

    airtime_rx INTEGER,

    airtime_tx INTEGER,

    raw_json TEXT NOT NULL,

    FOREIGN KEY(radio_snapshot_id)
        REFERENCES radio_snapshots(id)
);


CREATE TABLE IF NOT EXISTS radio_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    timestamp TEXT NOT NULL,

    ap_id TEXT NOT NULL,

    ap_name TEXT NOT NULL,

    interface_name TEXT NOT NULL,

    band TEXT NOT NULL,

    rssi REAL,

    channel_utilization REAL,

    station_count INTEGER,

    throughput_mbps REAL,

    packet_loss REAL,

    latency_ms REAL,

    interface_load REAL,

    score REAL
);

CREATE TABLE IF NOT EXISTS station_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    timestamp TEXT NOT NULL,

    station_mac TEXT NOT NULL,

    band TEXT NOT NULL,

    rssi REAL,

    clients INTEGER,

    airtime REAL
);
CREATE TABLE IF NOT EXISTS control_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    timestamp TEXT NOT NULL,

    ap_id TEXT NOT NULL,

    ap_name TEXT NOT NULL,

    interface_name TEXT NOT NULL,

    band TEXT,

    action_type TEXT NOT NULL,

    old_value INTEGER,

    new_value INTEGER,

    command_text TEXT NOT NULL,

    reason TEXT NOT NULL,

    status TEXT NOT NULL,

    response_json TEXT
);


CREATE TABLE IF NOT EXISTS wifi_sessions (
    id TEXT PRIMARY KEY,

    device_name TEXT NOT NULL,

    interface_name TEXT NOT NULL,

    ssid TEXT,

    station_mac TEXT NOT NULL,

    vendor TEXT,

    start_time TEXT,

    stop_time TEXT,

    raw_json TEXT NOT NULL
);


CREATE TABLE IF NOT EXISTS experiment_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    tag TEXT NOT NULL,

    phase TEXT NOT NULL
        CHECK(
            phase IN (
                'baseline',
                'control'
            )
        ),

    started_at TEXT NOT NULL,

    ended_at TEXT,

    note TEXT
);

"""


class Storage:

    def __init__(
        self,
        db_path: Path,
    ):

        self.db_path = db_path

        # Make sure parent directory exists.
        db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.connection = sqlite3.connect(
            str(db_path)
        )

        self.connection.row_factory = (
            sqlite3.Row
        )

    # ------------------------------------------------------------------
    # CLOSE
    # ------------------------------------------------------------------

    def close(
        self,
    ) -> None:

        self.connection.close()

    # ------------------------------------------------------------------
    # INIT
    # ------------------------------------------------------------------

    def init(
        self,
    ) -> None:

        self.connection.execute(
            "PRAGMA journal_mode=WAL"
        )

        self.connection.execute(
            "PRAGMA foreign_keys=ON"
        )

        self.connection.executescript(
            SCHEMA
        )

        self.connection.commit()

    # ------------------------------------------------------------------
    # SESSIONS
    # ------------------------------------------------------------------

    def start_session(
        self,
        tag: str,
        phase: str,
        timestamp: str,
        note: str = "",
    ) -> int:

        cursor = self.connection.execute(
            """
            INSERT INTO experiment_sessions(
                tag,
                phase,
                started_at,
                note
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                tag,
                phase,
                timestamp,
                note,
            ),
        )

        self.connection.commit()

        return int(
            cursor.lastrowid
        )

    def end_session(
        self,
        session_id: int,
        timestamp: str,
    ) -> None:

        self.connection.execute(
            """
            UPDATE experiment_sessions
            SET ended_at = ?
            WHERE id = ?
            """,
            (
                timestamp,
                session_id,
            ),
        )

        self.connection.commit()

    # ------------------------------------------------------------------
    # SNAPSHOT
    # ------------------------------------------------------------------

    def insert_snapshot(
        self,
        timestamp: str,
        ap_id: str,
        ap_name: str,
        radios: list[RadioState],
        raw_json: dict,
    ) -> None:

        cursor = self.connection.execute(
            """
            INSERT INTO poll_snapshots(
                timestamp,
                ap_id,
                ap_name,
                raw_json
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                timestamp,
                ap_id,
                ap_name,
                json.dumps(
                    raw_json,
                    default=str,
                ),
            ),
        )

        snapshot_id = cursor.lastrowid

        for radio in radios:

            radio_cursor = (
                self.connection.execute(
                    """
                    INSERT INTO radio_snapshots(
                        snapshot_id,
                        interface_name,
                        band,
                        ssid,
                        channel,
                        frequency,
                        tx_power,
                        noise,
                        htmode,
                        up,
                        client_count,
                        avg_signal,
                        total_airtime,
                        rx_bytes,
                        tx_bytes,
                        rx_packets,
                        tx_packets,
                        raw_json
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        snapshot_id,

                        radio.interface_name,
                        radio.band,

                        radio.ssid,
                        radio.channel,
                        radio.frequency,

                        radio.tx_power,
                        radio.noise,
                        radio.htmode,

                        int(
                            radio.up
                        ),

                        radio.client_count,
                        radio.avg_signal,

                        radio.total_airtime,

                        radio.rx_bytes,
                        radio.tx_bytes,

                        radio.rx_packets,
                        radio.tx_packets,

                        json.dumps(
                            radio.raw or {},
                            default=str,
                        ),
                    ),
                )
            )

            radio_snapshot_id = (
                radio_cursor.lastrowid
            )

            for client in (
                radio.clients or []
            ):

                mac = (
                    client.get(
                        "mac",
                        client.get(
                            "mac_address",
                            client.get(
                                "station_mac",
                                "",
                            ),
                        ),
                    )
                )

                vendor = client.get(
                    "vendor",
                    "",
                )

                signal = client.get(
                    "signal",
                    client.get(
                        "rssi"
                    ),
                )

                rate = (
                    client.get(
                        "rate",
                        {},
                    )
                    or {}
                )

                byte_values = (
                    client.get(
                        "bytes",
                        {},
                    )
                    or {}
                )

                packet_values = (
                    client.get(
                        "packets",
                        {},
                    )
                    or {}
                )

                airtime_values = (
                    client.get(
                        "airtime",
                        {},
                    )
                    or {}
                )

                self.connection.execute(
                    """
                    INSERT INTO station_snapshots(
                        radio_snapshot_id,
                        station_mac,
                        vendor,
                        signal,
                        rx_rate,
                        tx_rate,
                        rx_bytes,
                        tx_bytes,
                        rx_packets,
                        tx_packets,
                        airtime_rx,
                        airtime_tx,
                        raw_json
                    )
                    VALUES (
                        ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        radio_snapshot_id,

                        mac,

                        vendor,

                        signal,

                        int(
                            rate.get(
                                "rx",
                                0,
                            )
                            or 0
                        ),

                        int(
                            rate.get(
                                "tx",
                                0,
                            )
                            or 0
                        ),

                        int(
                            byte_values.get(
                                "rx",
                                0,
                            )
                            or 0
                        ),

                        int(
                            byte_values.get(
                                "tx",
                                0,
                            )
                            or 0
                        ),

                        int(
                            packet_values.get(
                                "rx",
                                0,
                            )
                            or 0
                        ),

                        int(
                            packet_values.get(
                                "tx",
                                0,
                            )
                            or 0
                        ),

                        int(
                            airtime_values.get(
                                "rx",
                                0,
                            )
                            or 0
                        ),

                        int(
                            airtime_values.get(
                                "tx",
                                0,
                            )
                            or 0
                        ),

                        json.dumps(
                            client,
                            default=str,
                        ),
                    ),
                )

        self.connection.commit()

    # ------------------------------------------------------------------
    # RADIO METRIC
    # ------------------------------------------------------------------

    def insert_radio_metric(
        self,
        timestamp: str,
        radio: RadioState,
    ) -> None:

        self.connection.execute(
            """
            INSERT INTO radio_metrics(
                timestamp,
                ap_id,
                ap_name,
                interface_name,
                band,
                rssi,
                channel_utilization,
                station_count,
                throughput_mbps,
                packet_loss,
                latency_ms,
                interface_load,
                score
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            """,
            (
                timestamp,

                radio.ap_id,
                radio.ap_name,

                radio.interface_name,
                radio.band,

                radio.avg_signal,

                radio.channel_utilization,

                radio.client_count,

                radio.throughput_mbps,

                radio.packet_loss,

                radio.latency_ms,

                radio.interface_load,

                radio.score,
            ),
        )

        self.connection.commit()

    # ------------------------------------------------------------------
    # CONTROL ACTION
    # ------------------------------------------------------------------

    def insert_action(
        self,
        timestamp: str,
        action: ControlAction,
        status: str,
        response: Any,
    ) -> None:

        self.connection.execute(
            """
            INSERT INTO control_actions(
                timestamp,
                ap_id,
                ap_name,
                interface_name,
                band,
                action_type,
                old_value,
                new_value,
                command_text,
                reason,
                status,
                response_json
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?
            )
            """,
            (
                timestamp,

                action.ap.device_id,
                action.ap.name,

                action.interface_name,
                action.band,

                action.action_type,

                action.old_value,
                action.new_value,

                action.command or "",

                action.reason or "",

                status,

                json.dumps(
                    response,
                    default=str,
                )
                if response is not None
                else None,
            ),
        )

        self.connection.commit()

    # ------------------------------------------------------------------
    # WIFI SESSIONS
    # ------------------------------------------------------------------

    def upsert_wifi_sessions(
        self,
        sessions: list[dict],
    ) -> None:

        for session in sessions:

            client = (
                session.get(
                    "client",
                    {},
                )
                or {}
            )

            session_id = session.get(
                "id"
            )

            if not session_id:
                continue

            self.connection.execute(
                """
                INSERT INTO wifi_sessions(
                    id,
                    device_name,
                    interface_name,
                    ssid,
                    station_mac,
                    vendor,
                    start_time,
                    stop_time,
                    raw_json
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?
                )

                ON CONFLICT(id)
                DO UPDATE SET
                    device_name=excluded.device_name,
                    interface_name=excluded.interface_name,
                    ssid=excluded.ssid,
                    station_mac=excluded.station_mac,
                    vendor=excluded.vendor,
                    start_time=excluded.start_time,
                    stop_time=excluded.stop_time,
                    raw_json=excluded.raw_json
                """,
                (
                    session_id,

                    session.get(
                        "device",
                        "",
                    ),

                    session.get(
                        "interface_name",
                        "",
                    ),

                    session.get(
                        "ssid",
                        "",
                    ),

                    client.get(
                        "mac_address",
                        client.get(
                            "mac",
                            "",
                        ),
                    ),

                    client.get(
                        "vendor",
                        "",
                    ),

                    session.get(
                        "start_time"
                    ),

                    session.get(
                        "stop_time"
                    ),

                    json.dumps(
                        session,
                        default=str,
                    ),
                ),
            )

        self.connection.commit()
    # ------------------------------------------------------------------
    # STATION METRIC
    # ------------------------------------------------------------------

    def insert_station_metric(
        self,
        timestamp: str,
        station: str,
        band: str,
        rssi: float | None,
        clients: int | None,
        airtime: float | None,
    ) -> None:

        self.connection.execute(
            """
            INSERT INTO station_metrics(
                timestamp,
                station_mac,
                band,
                rssi,
                clients,
                airtime
            )
            VALUES (
                ?, ?, ?, ?, ?, ?
            )
            """,
            (
                timestamp,
                station,
                band,
                rssi,
                clients,
                airtime,
            ),
        )

        self.connection.commit()    # ------------------------------------------------------------------
    # EXPORT
    # ------------------------------------------------------------------

    def export_radio_metrics_csv(
        self,
        output_path: Path,
        interface_name: str | None = None,
    ) -> None:

        query = """
        SELECT
            timestamp,
            ap_name,
            interface_name,
            band,
            rssi,
            channel_utilization,
            station_count,
            throughput_mbps,
            packet_loss,
            latency_ms,
            interface_load,
            score
        FROM radio_metrics
        """

        params: tuple[Any, ...] = ()

        if interface_name:

            query += """
            WHERE interface_name = ?
            """

            params = (
                interface_name,
            )

        query += """
        ORDER BY timestamp, interface_name
        """

        rows = (
            self.connection.execute(
                query,
                params,
            )
            .fetchall()
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with output_path.open(
            "w",
            newline="",
            encoding="utf-8",
        ) as handle:

            writer = csv.writer(
                handle
            )

            writer.writerow(
                [
                    "timestamp",
                    "ap_name",
                    "interface_name",
                    "band",
                    "rssi",
                    "channel_utilization",
                    "station_count",
                    "throughput_mbps",
                    "packet_loss",
                    "latency_ms",
                    "interface_load",
                    "score",
                ]
            )

            writer.writerows(
                [
                    tuple(row)
                    for row in rows
                ]
            )

    # Compatibility with your cli.py if it uses
    # the old method name.

    def export_radio_series_csv(
        self,
        output_path: Path,
        interface_name: str | None = None,
    ) -> None:

        self.export_radio_metrics_csv(
            output_path,
            interface_name,
        )
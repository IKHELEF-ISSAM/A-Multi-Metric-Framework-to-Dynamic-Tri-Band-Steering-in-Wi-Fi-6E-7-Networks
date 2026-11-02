"""Direct OpenWrt telemetry and guarded SSH operations (no OpenWISP)."""
from __future__ import annotations
import json
import re
import shlex
import subprocess
import time
from datetime import datetime, timezone
from typing import Any

_IF = re.compile(r'^[A-Za-z0-9_.-]+$')
_MAC = re.compile(r'^[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5}$')

def _num(text, key, cast=float):
    match = re.search(r'(?m)^\s*' + re.escape(key) + r':\s*(-?\d+(?:\.\d+)?)', text)
    return cast(float(match.group(1))) if match else None

class OpenWrtClient:
    def __init__(self, config: Any):
        self.config = config
        self.host = config.bpi_ssh_host
        self.user = config.bpi_ssh_user
        self.port = int(config.bpi_ssh_port)
        self.key = config.bpi_ssh_key
        self.timeout = float(config.bpi_ssh_timeout)
        self.apply = bool(config.bpi_allow_changes)
        self.radios = {r.interface_name: r for r in config.ap.radios}
        for iface, radio in self.radios.items():
            self._valid(iface)
            self._valid(radio.uci_radio)

    @staticmethod
    def _valid(value):
        if not _IF.fullmatch(str(value)) or str(value).startswith('-'):
            raise ValueError(f'Invalid OpenWrt identifier: {value!r}')
        return str(value)

    def _ssh(self, command: str, timeout=None) -> str:
        args = ['ssh', '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
                '-o', 'ConnectTimeout=5', '-p', str(self.port)]
        if self.key:
            args += ['-i', str(self.key)]
        args += ['--', f'{self.user}@{self.host}', command]
        result = subprocess.run(args, capture_output=True, text=True,
                                timeout=timeout or self.timeout, check=False)
        if result.returncode:
            raise RuntimeError(f'OpenWrt SSH failed ({result.returncode}): {result.stderr.strip()}')
        return result.stdout.strip()

    def _read(self, command: str) -> str:
        return self._ssh(command)

    def _radio(self, radio):
        iface = self._valid(radio.interface_name)
        q = shlex.quote(iface)
        info = self._read(f'iw dev {q} info')
        station_text = self._read(f'iw dev {q} station dump')
        try:
            uci = self._read(f'uci -q get wireless.{self._valid(radio.uci_radio)}.htmode')
        except RuntimeError:
            uci = ''
        stations = []
        for block in re.split(r'(?m)^Station\s+', station_text)[1:]:
            mac = block.split()[0].lower()
            if not _MAC.fullmatch(mac):
                continue
            signal = _num(block, 'signal', int)
            rx = _num(block, 'rx bytes', int) or 0
            tx = _num(block, 'tx bytes', int) or 0
            rx_packets = _num(block, 'rx packets', int) or 0
            tx_packets = _num(block, 'tx packets', int) or 0
            stations.append({'mac': mac, 'signal': signal, 'rssi': signal,
                             'rx_bytes': rx, 'tx_bytes': tx, 'rx_packets': rx_packets,
                             'tx_packets': tx_packets, 'rx_rate': _num(block, 'rx bitrate'),
                             'tx_rate': _num(block, 'tx bitrate'),
                             'airtime_rx': None, 'airtime_tx': None})
        channel = re.search(r'channel\s+(\d+)\s+\((\d+)\s+MHz\)', info)
        power = re.search(r'txpower\s+(-?\d+(?:\.\d+)?)\s+dBm', info)
        ssid = re.search(r'(?m)^\s*ssid\s+(.+)$', info)
        addr = re.search(r'(?m)^\s*addr\s+([0-9a-fA-F:]{17})', info)
        counters = {}
        for field in ('rx_bytes', 'tx_bytes', 'rx_packets', 'tx_packets'):
            try:
                counters[field] = int(self._read(f'cat /sys/class/net/{q}/statistics/{field}'))
            except (RuntimeError, ValueError):
                counters[field] = 0
        signals = [s['signal'] for s in stations if s['signal'] is not None]
        return {'interface_name': iface, 'band': radio.band,
                'ssid': ssid.group(1).strip() if ssid else '',
                'bssid': addr.group(1).lower() if addr else None,
                'channel': int(channel.group(1)) if channel else None,
                'frequency': int(channel.group(2)) if channel else None,
                'tx_power': round(float(power.group(1))) if power else None,
                'htmode': uci, 'up': True, 'clients': stations,
                'client_count': len(stations),
                'avg_signal': sum(signals)/len(signals) if signals else None,
                'total_airtime': 0.0, 'airtime_available': False,
                'noise': None, **counters}

    def get_monitoring_snapshot(self, ap=None):
        ap = ap or self.config.ap
        return {'type': 'DeviceMonitoring', 'id': ap.device_id,
                'name': ap.name, 'general': {'source': 'openwrt-ssh'},
                'interfaces': [self._radio(r) for r in ap.radios],
                'timestamp': datetime.now(timezone.utc).isoformat()}

    def get_device_monitoring(self, device_id, device_key=None):
        return self.get_monitoring_snapshot()

    def get_device(self, device_id):
        return {'id': device_id, 'name': self.config.ap.name, 'source': 'openwrt-ssh'}

    def get_device_config(self, device_id):
        return {'radios': [vars(r) for r in self.config.ap.radios]}

    def get_snapshot(self, device_id):
        monitoring = self.get_monitoring_snapshot()
        return {'id': device_id, 'name': self.config.ap.name, 'device': self.get_device(device_id),
                'data': monitoring, 'monitoring': monitoring, 'charts': [],
                'config': self.get_device_config(device_id)}

    def get_remote_radio_info(self, device_id, interface_name):
        if interface_name not in self.radios:
            raise ValueError('Unknown configured interface')
        return self._read(f'iw dev {shlex.quote(interface_name)} info')

    def execute_custom_command(self, device_id, command):
        # The legacy controller used arbitrary shell commands via OpenWISP.
        # Do not grant arbitrary remote shell execution in the replacement API.
        raise RuntimeError('Arbitrary remote shell commands are disabled; use guarded OpenWrt actions')

    def set_txpower(self, interface_name: str, dbm: int):
        radio = self.radios.get(interface_name)
        if radio is None:
            raise ValueError('Unknown configured interface')
        dbm = int(dbm)
        if not self.config.min_txpower <= dbm <= self.config.max_txpower:
            raise ValueError('TX power outside configured limits')
        cmd = f'uci set wireless.{self._valid(radio.uci_radio)}.txpower={dbm} && uci commit wireless && wifi reload'
        if not self.apply:
            return {'status': 'dry-run', 'command': cmd}
        return {'status': 'applied', 'output': self._ssh(cmd)}

    def disassociate(self, interface_name: str, mac: str):
        if interface_name not in self.radios or not _MAC.fullmatch(mac):
            raise ValueError('Invalid interface or station MAC')
        cmd = f'hostapd_cli -i {shlex.quote(interface_name)} disassociate {shlex.quote(mac)}'
        if not self.apply:
            return {'status': 'dry-run', 'command': cmd}
        return {'status': 'applied', 'output': self._ssh(cmd)}

    def list_wifi_sessions(self, **filters):
        # OpenWrt does not maintain the historical OpenWISP wifi-session API.
        # Return current associations only; caller should persist observations.
        now = datetime.now(timezone.utc).isoformat()
        result = []
        for radio in self.get_monitoring_snapshot()['interfaces']:
            for sta in radio['clients']:
                result.append({'id': f"{radio['interface_name']}:{sta['mac']}",
                               'device': self.config.ap.name, 'device_name': self.config.ap.name,
                               'client': {'mac_address': sta['mac'], 'vendor': ''},
                               'interface_name': radio['interface_name'],
                               'ssid': radio['ssid'], 'station_mac': sta['mac'],
                               'start_time': now, 'stop_time': None})
        return result

    def test_connection(self, device_id=None):
        return {'ok': True, 'source': 'openwrt-ssh', 'hostname': self._read('uname -n')}

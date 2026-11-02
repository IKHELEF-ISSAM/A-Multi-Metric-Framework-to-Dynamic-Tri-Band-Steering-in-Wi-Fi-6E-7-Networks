"""Offline checks: never execute SSH or contact an access point."""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wifi_steering.config import load_config
from wifi_steering.client import OpenWrtClient
from wifi_steering.storage import Storage
from wifi_steering.device_rules import DeviceRuleStore


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {
            'BPI_SSH_HOST': '192.0.2.1', 'BPI_ALLOW_CHANGES': 'false',
            'AP1_RADIO_2G_IFACE': 'phy0.0-ap0', 'AP1_RADIO_2G_UCI': 'radio0',
            'OPENWRT_DB_PATH': str(self.root/'test.sqlite3'),
            'OPENWRT_DEVICE_RULES_PATH': str(self.root/'rules.json'),
        }, clear=True)
        self.env.start()
        self.dotenv = patch('wifi_steering.config.load_dotenv')
        self.dotenv.start()

    def tearDown(self):
        self.dotenv.stop(); self.env.stop(); self.tmp.cleanup()

    def test_schema_initialization(self):
        cfg=load_config(); Storage(cfg.db_path).init()
        with sqlite3.connect(cfg.db_path) as db:
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({'poll_snapshots','radio_snapshots','station_snapshots'} <= tables)

    def test_client_dry_run_does_not_execute_ssh(self):
        client=OpenWrtClient(load_config())
        with patch.object(client,'_ssh',side_effect=AssertionError('SSH must not run')):
            self.assertEqual(client.set_txpower('phy0.0-ap0',15)['status'],'dry-run')
            self.assertEqual(client.disassociate('phy0.0-ap0','02:00:00:00:00:01')['status'],'dry-run')

    def test_rule_file_bootstrap(self):
        cfg=load_config(); DeviceRuleStore(cfg.device_rules_path)
        self.assertEqual(cfg.device_rules_path.read_text().strip(),'{}')

    def test_cli_apply_requires_explicit_flag(self):
        from wifi_steering.cli import main
        with patch('wifi_steering.cli.subprocess.run',side_effect=AssertionError('SSH must not run')):
            with self.assertRaises(SystemExit) as ctx:
                main(['run','--duration','1','--apply'])
        self.assertEqual(ctx.exception.code,2)

    def test_api_start_is_blocked_by_default(self):
        from wifi_steering import api
        with patch.object(api,'config',load_config()), patch.object(api.subprocess,'Popen',side_effect=AssertionError('must not start')):
            with self.assertRaisesRegex(RuntimeError,'BPI_ALLOW_CHANGES'):
                api.start_steering_process()


if __name__ == '__main__': unittest.main()

#!/usr/bin/env python3
"""
Unit tests for Second Brain dashboard sync engine (sync_dashboards.py).
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

try:
    import sync_dashboards
except ImportError:
    sync_dashboards = None


class TestSyncDashboards(unittest.TestCase):
    def test_module_exists(self):
        self.assertIsNotNone(sync_dashboards, "sync_dashboards module must exist")

    def test_format_dashboard_payload(self):
        payload = sync_dashboards.format_dashboard_payload(
            source='projects',
            name='Project Tracker',
            url='https://projects.nael.net',
            status='ok',
            summary={'open_tasks': 12, 'completed_today': 4}
        )
        self.assertEqual(payload['source'], 'projects')
        self.assertEqual(payload['status'], 'ok')
        self.assertFalse(payload['stale'])
        self.assertIn('fetched_at', payload)

    def test_detect_stale_dashboard(self):
        old_time = "2026-10-01T00:00:00Z"
        is_stale = sync_dashboards.is_timestamp_stale(old_time, max_hours=24)
        self.assertTrue(is_stale)


if __name__ == '__main__':
    unittest.main()

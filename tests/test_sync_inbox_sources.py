#!/usr/bin/env python3
"""
Unit tests for multi-inbox ingestion engine (sync_inbox_sources.py)
"""
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

try:
    import sync_inbox_sources
except ImportError:
    sync_inbox_sources = None


class TestSyncInboxSources(unittest.TestCase):
    def test_module_exists(self):
        self.assertIsNotNone(sync_inbox_sources, "sync_inbox_sources module must exist")

    def test_classify_email_job(self):
        msg = {
            'subject': 'Interview with Microsoft: Senior Account Technology Strategist',
            'from': 'recruiting@microsoft.com',
            'snippet': 'Your panel interview is scheduled for Wednesday at 9:00 AM.',
            'body': 'Hi Nael, looking forward to speaking with you regarding the Senior ATS role.'
        }
        res = sync_inbox_sources.classify_email(msg)
        self.assertEqual(res['category'], 'job')
        self.assertEqual(res['urgency'], 'high')

    def test_classify_email_bill(self):
        msg = {
            'subject': 'Your automatic payment of $4,083.90 is scheduled',
            'from': 'billing@safecu.org',
            'snippet': 'Property tax escrow payment processed on Nov 13.',
            'body': 'Your statement is ready. Payment amount: $4,083.90 due Nov 15.'
        }
        res = sync_inbox_sources.classify_email(msg)
        self.assertEqual(res['category'], 'bill')

    def test_classify_email_urgent_followup(self):
        msg = {
            'subject': 'Action required: sign severance agreement before Nov 30 deadline',
            'from': 'hr-benefits@amazon.com',
            'snippet': 'Please review and return the signed form ASAP.',
            'body': 'This is time-sensitive. Please review the attached termination documents.'
        }
        res = sync_inbox_sources.classify_email(msg)
        self.assertEqual(res['category'], 'followup')
        self.assertEqual(res['urgency'], 'urgent')

    def test_deduplicate_messages(self):
        msgs = [
            {'id': 'm1', 'subject': 'Tech Week Reminder', 'date': '2026-11-16T10:00:00Z'},
            {'id': 'm1', 'subject': 'Tech Week Reminder', 'date': '2026-11-16T10:00:00Z'},
            {'id': 'm2', 'subject': 'Different Event', 'date': '2026-11-16T11:00:00Z'}
        ]
        deduped = sync_inbox_sources.deduplicate_messages(msgs)
        self.assertEqual(len(deduped), 2)


if __name__ == '__main__':
    unittest.main()

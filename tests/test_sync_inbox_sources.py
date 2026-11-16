#!/usr/bin/env python3
"""
Unit tests for multi-inbox ingestion engine (sync_inbox_sources.py)
"""
import unittest
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

    def test_classify_email_job_actionable(self):
        msg = {
            'subject': 'Invitation to interview with Microsoft: Senior Account Technology Strategist',
            'from': 'recruiting@microsoft.com',
            'snippet': 'Your virtual interview is scheduled for Wednesday at 9:00 AM. Please confirm your availability.',
            'body': 'Hi Nael, looking forward to speaking with you regarding the Senior ATS role.'
        }
        res = sync_inbox_sources.classify_email(msg)
        self.assertTrue(res['is_actionable'])
        self.assertEqual(res['category'], 'job')

    def test_classify_email_bill_actionable(self):
        msg = {
            'subject': 'Your automatic payment of $4,083.90 is scheduled',
            'from': 'billing@safecu.org',
            'snippet': 'Property tax escrow payment processed on Nov 13.',
            'body': 'Your billing statement is ready. Payment due Nov 15: $4,083.90.'
        }
        res = sync_inbox_sources.classify_email(msg)
        self.assertTrue(res['is_actionable'])
        self.assertEqual(res['category'], 'bill')

    def test_classify_email_urgent_followup_actionable(self):
        msg = {
            'subject': 'Action required: sign closing documents before deadline',
            'from': 'escrow@firstam.com',
            'snippet': 'Please review and sign the attached loan disclosure documents ASAP.',
            'body': 'Response required today: review and sign.'
        }
        res = sync_inbox_sources.classify_email(msg)
        self.assertTrue(res['is_actionable'])
        self.assertEqual(res['category'], 'followup')
        self.assertEqual(res['urgency'], 'urgent')

    def test_classify_email_store_promo_discarded(self):
        promo_samples = [
            {'subject': 'STARTS NOW ✨ Buy One, Get One Free on Select Styles', 'snippet': 'Shop now for clearance deals. Unsubscribe here.'},
            {'subject': 'Find your favorite Nano-Air', 'snippet': 'New arrivals in stock now at Patagonia. Free shipping on $99+.'},
            {'subject': 'Thanksgiving Pre-Orders at Arizmendi Lakeshore 🍁', 'snippet': 'Place your bakery orders before we sell out!'},
            {'subject': 'New deals on Thule, Crocs, & more', 'snippet': 'Save up to 40% off your next purchase. View collection.'},
            {'subject': 'Feel the quality of the Wool Shop 🧣', 'snippet': 'Special discount inside. Limited time offer.'}
        ]
        for msg in promo_samples:
            res = sync_inbox_sources.classify_email(msg)
            self.assertFalse(res['is_actionable'], f"Promo should NOT be actionable: {msg['subject']}")
            self.assertEqual(res['category'], 'promo')

    def test_classify_email_newsletter_discarded(self):
        news_samples = [
            {'subject': '(Correction) The Post Most: Nearly a tenth of the S&P 500 is tied to three men', 'snippet': 'Daily digest from Washington Post. Unsubscribe here.'},
            {'subject': 'Rose Byrne and Meghann Fahy on trauma and truth', 'snippet': 'Latest podcast episode now live. Read the interview on Substack.'},
            {'subject': 'California sues OpenAI, alleging it endangered public safety', 'snippet': 'Daily newsletter tech edition.'},
            {'subject': 'Honcho Scheduled Maintenance: Nov 17-21', 'snippet': 'Notice of scheduled maintenance window. No action required.'}
        ]
        for msg in news_samples:
            res = sync_inbox_sources.classify_email(msg)
            self.assertFalse(res['is_actionable'], f"Newsletter should NOT be actionable: {msg['subject']}")

    def test_classify_email_job_digest_discarded(self):
        digest = {
            'subject': '10 new jobs matching your profile',
            'from': 'jobalerts-noreply@linkedin.com',
            'snippet': 'See jobs you may be interested in. Unsubscribe from job alerts.'
        }
        res = sync_inbox_sources.classify_email(digest)
        self.assertFalse(res['is_actionable'], "Automated job digest should NOT be actionable")

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

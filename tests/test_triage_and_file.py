#!/usr/bin/env python3
"""
Unit tests for Second Brain triage & filing engine (triage_and_file.py).
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

try:
    import triage_and_file
except ImportError:
    triage_and_file = None


class TestTriageAndFile(unittest.TestCase):
    def test_module_exists(self):
        self.assertIsNotNone(triage_and_file, "triage_and_file module must exist")

    def test_extract_job_details(self):
        capture = {
            'title': 'Interview with Microsoft: Senior Account Technology Strategist',
            'why': '[JOB] Recruiter panel interview scheduled for Wed Nov 18',
            'raw': 'From: recruiter@microsoft.com\nSnippet: Join the Teams call at 9:00 AM with hiring manager Sepideh.'
        }
        job = triage_and_file.extract_job(capture)
        self.assertIsNotNone(job)
        self.assertEqual(job['company'], 'Microsoft')
        self.assertIn('Strategist', job['role_title'])
        self.assertEqual(job['status'], 'interviewing')

    def test_extract_bill_details(self):
        capture = {
            'title': 'SAFE Credit Union statement: $4,083.90 paid from escrow',
            'why': '[BILL] Property tax escrow payment processed',
            'raw': 'Payee: SAFE Credit Union\nAmount: $4,083.90\nDue: 2026-11-15\nAutopay: yes'
        }
        bill = triage_and_file.extract_bill(capture)
        self.assertIsNotNone(bill)
        self.assertIn('SAFE Credit Union', bill['payee'])
        self.assertEqual(bill['amount_due'], 4083.90)
        self.assertEqual(bill['autopay'], 'yes')

    def test_extract_followup_details(self):
        capture = {
            'title': 'Action required: sign severance agreement before Nov 30 deadline',
            'why': '[FOLLOWUP] Severance documents review with Richard Amaechi',
            'raw': 'From: hr@amazon.com\nSnippet: Deadline is November 30, 2026.'
        }
        fu = triage_and_file.extract_followup(capture)
        self.assertIsNotNone(fu)
        self.assertIn('severance', fu['title'].lower())
        self.assertEqual(fu['status'], 'open')


if __name__ == '__main__':
    unittest.main()

#!/usr/bin/env python3
"""
Second Brain Triage & Filing Engine (triage_and_file.py)
Executed by the Librarian (role: librarian).
Triages new captures into:
- Job Search entries (/api/bot/jobs)
- Bills & Spend entries (/api/bot/bills)
- Actionable Follow-ups (/api/bot/followups)
- Permanent Notes (/api/bot/notes) for confirmed actionable items ONLY.

Safeguard:
Never files promotional emails, marketing blasts, newsletters, or generic ads as permanent notes.
Archived/ignored captures are updated to status: archived without filing notes.
"""

from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

HOME = os.path.expanduser('~')
BRAIN_SH = os.path.join(HOME, 'second-brain', 'brain.sh')

KNOWN_COMPANIES = [
    'Microsoft', 'NVIDIA', 'Nvidia', 'Google', 'Intuit', 'Amazon', 'Apple',
    'OpenAI', 'Anthropic', 'Meta', 'Cloudflare', 'F5', 'CoreWeave', 'TypeSafe',
    'Nutanix', 'Dragonfly AI', 'Pluto TV', 'SAFE Credit Union', 'Capital One'
]

# Strict discard patterns for triage
RE_PROMO_DISCARD = re.compile(
    r'\b(sale|discount|deal|deals|coupon|promo|promotions|pre-order|starts now|'
    r'black friday|cyber monday|buy one|bogo|clearance|off your next|free shipping|'
    r'newsletter|daily digest|weekly digest|the post most|morning brew|substack|'
    r'jobs matching your profile|jobs you may be interested|new jobs alert|daily job alert)\b',
    re.I
)


def extract_job(capture: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    combined = f"{capture.get('title', '')} {capture.get('why', '')} {capture.get('raw', '')}"
    
    # Reject promotional digests and automated job boards
    if RE_PROMO_DISCARD.search(combined):
        return None

    if not re.search(r'\b(interview|invitation to interview|screening call|technical screen|technical panel|onsite|recruiter reached out|recruiting coordinator|job offer|offer letter)\b', combined, re.I):
        return None

    # Detect company
    company = "Opportunity"
    for c in KNOWN_COMPANIES:
        if re.search(rf'\b{c}\b', combined, re.I):
            company = c
            break

    # Detect role title
    role_title = "Technology Lead"
    m_role = re.search(r'(?:role|for|position|as)\s+([A-Z][A-Za-z0-9\s\-/]{3,40})(?:\.|\n|\)|,|$)', combined)
    if m_role:
        role_title = m_role.group(1).strip()
    elif 'Senior Account Technology Strategist' in combined:
        role_title = 'Senior Account Technology Strategist'
    elif 'Field Technologist' in combined:
        role_title = 'Global Field Technologist'
    elif 'Engineer' in combined:
        role_title = 'Senior Software Engineer'

    # Detect status
    status = 'active'
    if re.search(r'\b(interview|panel|onsite)\b', combined, re.I):
        status = 'interviewing'
    elif re.search(r'\b(screening|intro call)\b', combined, re.I):
        status = 'screening'
    elif re.search(r'\b(offer)\b', combined, re.I):
        status = 'offer'
    elif re.search(r'\b(applied|submitted)\b', combined, re.I):
        status = 'applied'

    return {
        'company': company,
        'role_title': role_title,
        'status': status,
        'next_action': 'Prepare briefing and interview answers',
        'notes': capture.get('why', '')[:500]
    }


def extract_bill(capture: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    combined = f"{capture.get('title', '')} {capture.get('why', '')} {capture.get('raw', '')}"
    
    # Reject store promo claiming bill/sale
    if re.search(r'\b(sale|discount|coupon|buy one|bogo|clearance)\b', combined, re.I):
        return None

    if not re.search(r'\b(bill due|invoice|payment due|statement is ready|autopay scheduled|automatic payment scheduled|property tax|utility bill|billing statement|past due)\b', combined, re.I):
        return None

    # Parse payee
    payee = "Recurring Vendor"
    for c in KNOWN_COMPANIES:
        if re.search(rf'\b{c}\b', combined, re.I):
            payee = c
            break

    # Parse amount
    amount_due = 0.0
    m_amt = re.search(r'\$\s*([0-9,]+(?:\.[0-9]{2})?)', combined)
    if m_amt:
        try:
            amount_due = float(m_amt.group(1).replace(',', ''))
        except ValueError:
            amount_due = 0.0

    # If no amount could be extracted, do not treat as actionable bill entry
    if amount_due <= 0.0:
        return None

    # Parse autopay
    autopay = 'unknown'
    if re.search(r'\b(auto-?pay|automatic payment|autopay is on|paid from escrow)\b', combined, re.I):
        autopay = 'yes'
    elif re.search(r'\b(manual|not enrolled in autopay)\b', combined, re.I):
        autopay = 'no'

    # Status
    status = 'open'
    if re.search(r'\b(paid|processed|thank you for your payment)\b', combined, re.I):
        status = 'paid'

    return {
        'payee': payee,
        'amount_due': amount_due,
        'autopay': autopay,
        'status': status,
        'notes': capture.get('why', '')[:300]
    }


def extract_followup(capture: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    combined = f"{capture.get('title', '')} {capture.get('why', '')} {capture.get('raw', '')}"
    
    # Reject marketing digests and newsletters
    if RE_PROMO_DISCARD.search(combined) or re.search(r'\b(unsubscribe|email preferences|view in browser)\b', combined, re.I):
        return None

    if not re.search(r'\b(action required|action needed|please reply|please respond|response required|time-sensitive|rsvp requested|confirm your attendance|review and sign|signature requested|document awaiting signature|unauthorized login|suspicious sign-in)\b', combined, re.I):
        return None

    title = capture.get('title', 'Action needed')
    who = 'External'
    m_from = re.search(r'From:\s*([^<\n]+)', capture.get('raw', ''))
    if m_from:
        who = m_from.group(1).strip()[:40]

    return {
        'title': title[:150],
        'who': who,
        'due_date': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'status': 'open',
        'notes': capture.get('why', '')[:300]
    }


def run_brain_cmd(method: str, path: str, data: Optional[Dict[str, Any]] = None, role: str = 'librarian') -> Optional[Dict[str, Any]]:
    """Helper to run brain.sh and parse JSON response."""
    if not os.path.exists(BRAIN_SH):
        return None
    cmd = [BRAIN_SH, method, path]
    if data is not None:
        cmd.append(json.dumps(data))
    else:
        cmd.append('')
    cmd.append(role)
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout.strip())
        return None
    except Exception as e:
        print(f"[ERROR] brain.sh {method} {path} failed: {e}", file=sys.stderr)
        return None


def main():
    parser = argparse.ArgumentParser(description="Second Brain Triage & Filing Engine")
    parser.add_argument('--dry-run', action='store_true', help="Inspect and simulate without committing to D1")
    args = parser.parse_args()

    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting Librarian Filing (dry_run={args.dry_run})...")

    # 1. Fetch new captures
    captures = run_brain_cmd('GET', '/api/bot/captures')
    if not captures or not isinstance(captures, list):
        print("  - No captures retrieved from Second Brain.")
        return

    new_captures = [c for c in captures if c.get('status') == 'new']
    print(f"  - Found {len(new_captures)} new captures needing filing")

    filed_jobs = 0
    filed_bills = 0
    filed_followups = 0
    filed_notes = 0
    archived_non_actionables = 0

    for c in new_captures:
        cid = c.get('id')
        title = c.get('title', 'Untitled')
        why = c.get('why', '')

        # Check job
        job_data = extract_job(c)
        if job_data:
            if not args.dry_run:
                run_brain_cmd('POST', '/api/bot/jobs', job_data, role='librarian')
            filed_jobs += 1

        # Check bill
        bill_data = extract_bill(c)
        if bill_data and bill_data['amount_due'] > 0:
            if not args.dry_run:
                run_brain_cmd('POST', '/api/bot/bills', bill_data, role='librarian')
            filed_bills += 1

        # Check followup
        fu_data = extract_followup(c)
        if fu_data:
            if not args.dry_run:
                run_brain_cmd('POST', '/api/bot/followups', fu_data, role='librarian')
            filed_followups += 1

        # Only file a permanent note if an actionable entity was confirmed
        is_actionable = (job_data is not None) or (bill_data is not None and bill_data['amount_due'] > 0) or (fu_data is not None)

        if is_actionable:
            note_tag = 'job' if job_data else ('bill' if bill_data else 'followup')
            note_data = {
                'title': title,
                'body': f"{why}\n\nSource: {c.get('source_url', 'email')}\n\n{c.get('raw', '')}",
                'tags': ['inbox', 'filed', note_tag],
                'owner': 'librarian',
                'stage': 'filed',
                'status': 'active'
            }
            if not args.dry_run:
                run_brain_cmd('POST', '/api/bot/notes', note_data, role='librarian')
                run_brain_cmd('PATCH', f'/api/bot/captures/{cid}', {'status': 'filed'}, role='librarian')
            filed_notes += 1
        else:
            # Capture is not an actionable job/bill/followup -> archive it, DO NOT file note
            archived_non_actionables += 1
            if not args.dry_run:
                run_brain_cmd('PATCH', f'/api/bot/captures/{cid}', {'status': 'archived'}, role='librarian')

    # Log to change log
    summary_text = f"Librarian filed {filed_notes} actionable notes ({filed_jobs} jobs, {filed_bills} bills, {filed_followups} followups); archived {archived_non_actionables} non-actionables"
    if not args.dry_run and (filed_notes > 0 or archived_non_actionables > 0):
        run_brain_cmd('POST', '/api/bot/changes', {
            'action': 'filing',
            'entity': 'captures',
            'entity_id': 'batch',
            'summary': summary_text
        }, role='librarian')

    print(f"Filing complete: {summary_text} (dry_run={args.dry_run})")


if __name__ == '__main__':
    main()

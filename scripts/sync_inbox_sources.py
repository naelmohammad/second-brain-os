#!/usr/bin/env python3
"""
Multi-Inbox Extraction Engine (sync_inbox_sources.py)
Ingests emails across user accounts:
- nael@nael.org & naelmohammad@gmail.com (Google Workspace / Gmail API)
- naelmohammad@hotmail.com (Microsoft Graph / Outlook IMAP)
- naelm@yahoo.com (Yahoo IMAP)

High-Value Actionable Intake:
Filters strictly for actionable items (bills, interview/job requests, explicit action-needed followups).
Discards all promotions, newsletters, advertisements, retail deals, and mass digests.
"""

from __future__ import annotations
import argparse
import imaplib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from email import policy
from email.parser import BytesParser
from typing import Any, Dict, List, Optional

# --- Configuration & Paths ---
HOME = os.path.expanduser('~')
BRAIN_SH = os.path.join(HOME, 'second-brain', 'brain.sh')
GWS_SCRIPT = os.path.join(HOME, '.hermes', 'skills', 'productivity', 'google-workspace', 'scripts', 'google_api.py')
GWS_VENV_PYTHON = os.path.join(HOME, '.hermes', 'environments', 'google-workspace', 'gen-6206d2ffc46044ddae6a6ce5f5d336cf', 'venv', 'bin', 'python')

# --- High-Value Actionable Classification Rules ---

# Strict promotional, sales, marketing, and newsletter signals to reject
RE_PROMO_DISCARD = re.compile(
    r'\b('
    # Store sales & deals
    r'sale|sales|discount|discounts|deal|deals|coupon|coupons|promo|promos|promotions?|pre-orders?|starts now|'
    r'black friday|cyber monday|buy one|bogo|clearance|off your next|% off|free shipping|'
    r'free gift|gift guide|rewards|cashback|cash back|shop now|view collection|new arrivals|'
    r'holiday gift|limited time|order now|special offer|exclusive offer|'
    # Newsletters, blogs, and media blasts
    r'newsletter|daily digest|weekly digest|weekly roundup|edition|the post most|morning brew|'
    r'tldr|substack|breaking news|special report|podcast|episode|webinar|sponsored|press release|'
    # Job digests & automated board notifications (not individual recruiters)
    r'jobs matching your profile|jobs you may be interested in|new jobs alert|daily job alert|'
    r'weekly job roundup|recommended jobs|glassdoor jobs|indeed job alert|linkedin job alerts|'
    # System notifications that are purely informational
    r'scheduled maintenance|maintenance window|planned downtime|system maintenance|outage report'
    r')\b',
    re.I
)

# Unsubscribe / marketing headers or body signals
RE_MARKETING_SIGNALS = re.compile(
    r'\b(unsubscribe|opt out|manage preferences|view in browser|email preferences|privacy policy|forward to a friend)\b',
    re.I
)

# Actionable: Job Interview or Recruitment (direct human recruiter / application status)
RE_JOB_ACTIONABLE = re.compile(
    r'\b('
    r'invitation to interview|schedule an interview|interview request|interview with|'
    r'screening call|technical screen|technical panel|onsite interview|virtual interview|'
    r'next steps in your application|status of your application|job offer|offer letter|'
    r'recruiter reached out|recruiting coordinator'
    r')\b',
    re.I
)

# Actionable: Bills & Invoices (requires genuine bill, payment notice, or invoice)
RE_BILL_ACTIONABLE = re.compile(
    r'\b('
    r'bill due|invoice|payment due|statement is ready|autopay scheduled|automatic payment scheduled|'
    r'amount due|minimum payment due|property tax|utility bill|billing statement|past due|'
    r'payment confirmation|payment processed|tax notice'
    r')\b',
    re.I
)

# Actionable: Direct Action Required / Follow-up / Signature
RE_FOLLOWUP_ACTIONABLE = re.compile(
    r'\b('
    r'action required|action needed|please reply|please respond|response required|'
    r'time-sensitive|urgent response|rsvp requested|confirm your attendance|'
    r'review and sign|signature requested|document awaiting signature|'
    r'unauthorized login|security alert: new login|suspicious sign-in'
    r')\b',
    re.I
)


def classify_email(msg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates an email for high-value actionability.
    Returns is_actionable=True ONLY if the email is a confirmed bill,
    recruiter/interview action item, or direct follow-up request.
    All ads, promos, retail deals, newsletters, and general blasts return is_actionable=False.
    """
    subject = (msg.get('subject') or '').strip()
    from_addr = (msg.get('from') or '').strip()
    snippet = (msg.get('snippet') or '').strip()
    body = (msg.get('body') or '').strip()
    combined = f"{subject} {from_addr} {snippet} {body}".lower()

    # Step 1: Immediate check for high-confidence promotional/marketing discard
    is_promo_match = bool(RE_PROMO_DISCARD.search(combined))
    has_unsubscribe = bool(RE_MARKETING_SIGNALS.search(combined))

    # Step 2: Check for actionable categories
    is_bill = bool(RE_BILL_ACTIONABLE.search(combined))
    is_job = bool(RE_JOB_ACTIONABLE.search(combined)) and not re.search(r'\b(jobs matching|alert|digest|recommended)\b', combined, re.I)
    is_followup = bool(RE_FOLLOWUP_ACTIONABLE.search(combined))

    # If it matched marketing/promo and is NOT a bill or direct job interview, discard immediately
    if is_promo_match:
        if not is_bill and not is_job:
            return {
                'is_actionable': False,
                'category': 'promo',
                'urgency': 'low',
                'why': f"Promotional or marketing message discarded: {subject}",
                'subject': subject,
                'from': from_addr
            }

    # Step 3: Classify into actionable categories
    if is_job:
        return {
            'is_actionable': True,
            'category': 'job',
            'urgency': 'high' if re.search(r'\b(today|tomorrow|urgent|schedule)\b', combined, re.I) else 'normal',
            'why': f"Recruitment / Interview action item: {subject}",
            'subject': subject,
            'from': from_addr
        }

    if is_bill:
        # Extra check: make sure it's not a store sale claiming 'bill'
        if re.search(r'\b(sale|shop|discount|buy|cart)\b', combined, re.I) and not re.search(r'(\$\s*[0-9]+|amount|payment|invoice)', combined, re.I):
            return {
                'is_actionable': False,
                'category': 'promo',
                'urgency': 'low',
                'why': f"Store promotion discarded: {subject}",
                'subject': subject,
                'from': from_addr
            }
        return {
            'is_actionable': True,
            'category': 'bill',
            'urgency': 'high' if re.search(r'\b(past due|due today|overdue|penalty)\b', combined, re.I) else 'normal',
            'why': f"Financial bill or payment notice: {subject}",
            'subject': subject,
            'from': from_addr
        }

    if is_followup:
        # If it has marketing/unsubscribe signals, it's likely a newsletter claiming 'action required' or 'reminder'
        if has_unsubscribe:
            return {
                'is_actionable': False,
                'category': 'promo',
                'urgency': 'low',
                'why': f"Bulk marketing email discarded: {subject}",
                'subject': subject,
                'from': from_addr
            }
        return {
            'is_actionable': True,
            'category': 'followup',
            'urgency': 'urgent' if re.search(r'\b(urgent|asap|today|unauthorized)\b', combined, re.I) else 'high',
            'why': f"Action required / Time-sensitive request: {subject}",
            'subject': subject,
            'from': from_addr
        }

    # Everything else (newsletters, receipts, random correspondence, informational alerts) is DISCARDED
    return {
        'is_actionable': False,
        'category': 'ignored',
        'urgency': 'low',
        'why': f"Non-actionable message discarded: {subject}",
        'subject': subject,
        'from': from_addr
    }


def deduplicate_messages(msgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []
    for m in msgs:
        mid = m.get('id')
        if not mid:
            subj = (m.get('subject') or '').strip().lower()
            date = m.get('date') or ''
            mid = f"{subj}:{date}"
        if mid not in seen:
            seen.add(mid)
            deduped.append(m)
    return deduped


# --- Mailbox Collectors ---

def fetch_google_workspace_messages(max_results: int = 50) -> List[Dict[str, Any]]:
    """Fetch messages from Google Workspace (nael@nael.org and aliases)."""
    if not os.path.exists(GWS_VENV_PYTHON) or not os.path.exists(GWS_SCRIPT):
        print("[WARN] Google Workspace script or venv not found", file=sys.stderr)
        return []

    try:
        cmd = [GWS_VENV_PYTHON, GWS_SCRIPT, 'gmail', 'search', 'newer_than:2d', '--max', str(max_results)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        if res.returncode != 0:
            print(f"[WARN] Gmail search returned error: {res.stderr.strip()}", file=sys.stderr)
            return []
        data = json.loads(res.stdout)
        messages = []
        for item in data:
            messages.append({
                'source': 'gmail',
                'account': item.get('to', 'nael@nael.org'),
                'id': item.get('id'),
                'threadId': item.get('threadId'),
                'from': item.get('from', ''),
                'to': item.get('to', ''),
                'subject': item.get('subject', ''),
                'date': item.get('date', ''),
                'snippet': item.get('snippet', ''),
                'labels': item.get('labels', [])
            })
        return messages
    except Exception as e:
        print(f"[WARN] Failed to fetch Google Workspace messages: {e}", file=sys.stderr)
        return []


def resolve_keychain_password(account: str, service: str = 'Hermes') -> Optional[str]:
    try:
        res = subprocess.run(
            ['/usr/bin/security', 'find-generic-password', '-a', account, '-s', service, '-w'],
            capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    return None


def fetch_hotmail_messages(max_results: int = 50) -> List[Dict[str, Any]]:
    """Fetch from Outlook/Hotmail IMAP (outlook.office365.com)."""
    user = 'naelmohammad@hotmail.com'
    password = os.environ.get('HOTMAIL_PASSWORD') or resolve_keychain_password('HOTMAIL_PASSWORD')
    if not password:
        return []

    messages = []
    try:
        mail = imaplib.IMAP4_SSL('outlook.office365.com', 993)
        mail.login(user, password)
        mail.select('INBOX', readonly=True)
        _, data = mail.search(None, 'UNSEEN')
        id_list = data[0].split()
        if not id_list:
            _, data = mail.search(None, 'ALL')
            id_list = data[0].split()[-max_results:]
        else:
            id_list = id_list[-max_results:]

        for num in id_list:
            _, msg_data = mail.fetch(num, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = BytesParser(policy=policy.default).parsebytes(response_part[1])
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == 'text/plain':
                                body = part.get_content()
                                break
                    else:
                        body = msg.get_content()

                    messages.append({
                        'source': 'hotmail',
                        'account': user,
                        'id': f"hm_{num.decode()}",
                        'from': msg['from'],
                        'to': msg['to'],
                        'subject': msg['subject'],
                        'date': msg['date'],
                        'snippet': body[:200] if body else '',
                        'body': body[:1000] if body else ''
                    })
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"[WARN] Hotmail IMAP fetch failed: {e}", file=sys.stderr)
    return messages


def fetch_yahoo_messages(max_results: int = 50) -> List[Dict[str, Any]]:
    """Fetch from Yahoo IMAP (export.imap.mail.yahoo.com)."""
    user = 'naelm@yahoo.com'
    password = os.environ.get('YAHOO_APP_PASSWORD') or resolve_keychain_password('YAHOO_APP_PASSWORD')
    if not password:
        return []

    messages = []
    try:
        mail = imaplib.IMAP4_SSL('export.imap.mail.yahoo.com', 993)
        mail.login(user, password)
        mail.select('INBOX', readonly=True)
        _, data = mail.search(None, 'UNSEEN')
        id_list = data[0].split()
        if not id_list:
            _, data = mail.search(None, 'ALL')
            id_list = data[0].split()[-max_results:]
        else:
            id_list = id_list[-max_results:]

        for num in id_list:
            _, msg_data = mail.fetch(num, '(RFC822)')
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = BytesParser(policy=policy.default).parsebytes(response_part[1])
                    body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == 'text/plain':
                                body = part.get_content()
                                break
                    else:
                        body = msg.get_content()

                    messages.append({
                        'source': 'yahoo',
                        'account': user,
                        'id': f"yh_{num.decode()}",
                        'from': msg['from'],
                        'to': msg['to'],
                        'subject': msg['subject'],
                        'date': msg['date'],
                        'snippet': body[:200] if body else '',
                        'body': body[:1000] if body else ''
                    })
        mail.close()
        mail.logout()
    except Exception as e:
        print(f"[WARN] Yahoo IMAP fetch failed: {e}", file=sys.stderr)
    return messages


def get_existing_captures() -> set[str]:
    """Retrieve existing capture source_urls and titles to prevent re-capturing."""
    if not os.path.exists(BRAIN_SH):
        return set()
    cmd = [BRAIN_SH, 'GET', '/api/bot/captures', '', 'scout']
    seen = set()
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            captures = json.loads(res.stdout)
            for c in captures:
                if c.get('source_url'):
                    seen.add(c['source_url'].strip().lower())
                if c.get('title'):
                    seen.add(c['title'].strip().lower())
    except Exception as e:
        print(f"[WARN] Could not retrieve existing captures: {e}", file=sys.stderr)
    return seen


def post_capture(title: str, source_url: str, why: str, raw: str, next_owner: str = 'librarian') -> bool:
    """Post a new capture to Second Brain via brain.sh with role scout."""
    if not os.path.exists(BRAIN_SH):
        return False
    payload = json.dumps({
        'title': title[:200],
        'source_url': source_url,
        'source_type': 'email',
        'why': why,
        'next_owner': next_owner,
        'raw': raw[:2000]
    })
    try:
        subprocess.run([BRAIN_SH, 'POST', '/api/bot/captures', payload, 'scout'], check=True, timeout=10, capture_output=True)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to post capture '{title}': {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="Multi-Inbox Ingestion Engine for Second Brain")
    parser.add_argument('--dry-run', action='store_true', help="Scan and classify without publishing to D1")
    parser.add_argument('--limit', type=int, default=50, help="Max emails to scan per provider")
    args = parser.parse_args()

    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting Multi-Inbox Sync (dry_run={args.dry_run})...")

    # 1. Fetch from all sources
    all_raw: List[Dict[str, Any]] = []
    
    # Google Workspace (nael@nael.org, naelmohammad@gmail.com)
    gws_msgs = fetch_google_workspace_messages(max_results=args.limit)
    print(f"  - Google Workspace / Gmail: found {len(gws_msgs)} messages")
    all_raw.extend(gws_msgs)

    # Hotmail (naelmohammad@hotmail.com)
    hm_msgs = fetch_hotmail_messages(max_results=args.limit)
    print(f"  - Hotmail (naelmohammad@hotmail.com): found {len(hm_msgs)} messages")
    all_raw.extend(hm_msgs)

    # Yahoo (naelm@yahoo.com)
    yh_msgs = fetch_yahoo_messages(max_results=args.limit)
    print(f"  - Yahoo (naelm@yahoo.com): found {len(yh_msgs)} messages")
    all_raw.extend(yh_msgs)

    # 2. Deduplicate
    unique_msgs = deduplicate_messages(all_raw)
    print(f"  - Total unique messages across sources: {len(unique_msgs)}")

    # 3. Classify and filter
    existing_captures = get_existing_captures()
    actionable_count = 0
    posted_count = 0
    discarded_count = 0

    for msg in unique_msgs:
        classification = classify_email(msg)
        if not classification.get('is_actionable'):
            discarded_count += 1
            continue

        subj = msg.get('subject', 'Untitled Email').strip()
        from_hdr = msg.get('from', '')
        source_url = f"email://{msg.get('source', 'mail')}/{msg.get('id', '')}"
        cat = classification['category']

        # Check duplicate
        if source_url.lower() in existing_captures or subj.lower() in existing_captures:
            continue

        actionable_count += 1
        why = f"[{cat.upper()}] {classification['why']}"
        raw = f"From: {from_hdr}\nDate: {msg.get('date', '')}\nAccount: {msg.get('account', '')}\nSnippet: {msg.get('snippet', '')}"

        if args.dry_run:
            print(f"    [DRY-RUN] Found actionable: {subj} (cat: {cat}, urgency: {classification['urgency']})")
        else:
            ok = post_capture(title=subj, source_url=source_url, why=why, raw=raw, next_owner='librarian')
            if ok:
                posted_count += 1
                existing_captures.add(subj.lower())
                existing_captures.add(source_url.lower())

    status_summary = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'scanned': len(unique_msgs),
        'actionable': actionable_count,
        'discarded_non_actionable': discarded_count,
        'posted': posted_count,
        'dry_run': args.dry_run
    }
    print(f"Sync complete: {json.dumps(status_summary)}")


if __name__ == '__main__':
    main()

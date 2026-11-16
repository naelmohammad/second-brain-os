#!/usr/bin/env python3
"""
Multi-Inbox Extraction Engine (sync_inbox_sources.py)
Ingests emails across user accounts:
- nael@nael.org & naelmohammad@gmail.com (Google Workspace / Gmail API)
- naelmohammad@hotmail.com (Microsoft Graph / Outlook IMAP)
- naelm@yahoo.com (Yahoo IMAP)

Classifies, deduplicates, and creates Second Brain captures via brain.sh.
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

# --- Classification Rules ---
RE_JOB = re.compile(r'\b(interview|interviews|recruiter|recruiting|offer|hiring|headhunter|application|applied|screening|technical panel|onsite|candidate)\b', re.I)
RE_BILL = re.compile(r'\b(bill|invoice|statement|due date|payment due|autopay|automatic payment|receipt|escrow|renewal|subscription)\b', re.I)
RE_FOLLOWUP = re.compile(r'\b(deadline|action required|urgent|please reply|time-sensitive|reminder|asap|review and sign|rsvp|check-in)\b', re.I)
RE_PROMO_SPAM = re.compile(r'\b(unsub|unsubscribe|opt out|promo|sale|discount|deal of the day|newsletter|marketing)\b', re.I)


def classify_email(msg: Dict[str, Any]) -> Dict[str, Any]:
    subject = msg.get('subject', '') or ''
    from_addr = msg.get('from', '') or ''
    snippet = msg.get('snippet', '') or ''
    body = msg.get('body', '') or ''
    combined = f"{subject} {from_addr} {snippet} {body}".lower()

    # Default category & urgency
    category = 'general'
    urgency = 'normal'
    why = 'General correspondence'

    if RE_JOB.search(combined):
        category = 'job'
        urgency = 'high' if re.search(r'\b(interview|offer|onsite|screening|today|tomorrow)\b', combined, re.I) else 'normal'
        why = f"Job lead or recruitment update: {subject}"
    elif RE_BILL.search(combined):
        category = 'bill'
        urgency = 'high' if re.search(r'\b(due|past due|overdue|penalty)\b', combined, re.I) else 'normal'
        why = f"Financial statement or billing item: {subject}"
    elif RE_FOLLOWUP.search(combined):
        category = 'followup'
        urgency = 'urgent' if re.search(r'\b(asap|today|deadline|urgent|action required)\b', combined, re.I) else 'high'
        why = f"Time-sensitive action or deadline: {subject}"
    elif RE_PROMO_SPAM.search(combined) and not re.search(r'\b(receipt|order confirmation|shipped)\b', combined, re.I):
        category = 'promo'
        urgency = 'low'
        why = 'Promotional or marketing message'

    return {
        'category': category,
        'urgency': urgency,
        'why': why,
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
        print(f"[WARN] Error fetching from Google Workspace: {e}", file=sys.stderr)
        return []


def get_keychain_password(account: str, service: str = "Hermes") -> Optional[str]:
    """Safely fetch password or token from macOS Keychain."""
    try:
        val = subprocess.check_output(
            ['/usr/bin/security', 'find-generic-password', '-a', account, '-s', service, '-w'],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        return val if val else None
    except Exception:
        try:
            val = subprocess.check_output(
                ['/usr/bin/security', 'find-internet-password', '-a', account, '-w'],
                stderr=subprocess.DEVNULL
            ).decode().strip()
            return val if val else None
        except Exception:
            return None


def fetch_hotmail_messages(max_results: int = 20) -> List[Dict[str, Any]]:
    """Fetch recent messages from Outlook / Hotmail (naelmohammad@hotmail.com)."""
    pwd = get_keychain_password('naelmohammad@hotmail.com') or os.environ.get('HOTMAIL_PASSWORD')
    if not pwd:
        # Check if Graph token cache is readable or report auth pending
        return []

    try:
        mail = imaplib.IMAP4_SSL('outlook.office365.com', 993, timeout=10)
        mail.login('naelmohammad@hotmail.com', pwd)
        mail.select('INBOX', readonly=True)
        _, data = mail.search(None, '(UNSEEN)')
        msg_ids = data[0].split()[-max_results:] if data and data[0] else []
        messages = []
        for mid in msg_ids:
            _, mdata = mail.fetch(mid, '(RFC822)')
            if mdata and mdata[0]:
                raw_email = mdata[0][1]
                parsed = BytesParser(policy=policy.default).parsebytes(raw_email)
                messages.append({
                    'source': 'hotmail',
                    'account': 'naelmohammad@hotmail.com',
                    'id': f"hotmail-{mid.decode()}",
                    'from': parsed.get('From', ''),
                    'to': parsed.get('To', ''),
                    'subject': parsed.get('Subject', ''),
                    'date': parsed.get('Date', ''),
                    'snippet': parsed.get_body(preferencelist=('plain', 'html')).get_content()[:200] if parsed.get_body() else ''
                })
        mail.close()
        mail.logout()
        return messages
    except Exception as e:
        print(f"[INFO] Hotmail ingestion status: {e}", file=sys.stderr)
        return []


def fetch_yahoo_messages(max_results: int = 20) -> List[Dict[str, Any]]:
    """Fetch recent messages from Yahoo (naelm@yahoo.com)."""
    pwd = get_keychain_password('naelm@yahoo.com') or get_keychain_password('YAHOO_APP_PASSWORD') or os.environ.get('YAHOO_APP_PASSWORD')
    if not pwd:
        return []

    try:
        mail = imaplib.IMAP4_SSL('imap.mail.yahoo.com', 993, timeout=10)
        mail.login('naelm@yahoo.com', pwd)
        mail.select('INBOX', readonly=True)
        _, data = mail.search(None, '(UNSEEN)')
        msg_ids = data[0].split()[-max_results:] if data and data[0] else []
        messages = []
        for mid in msg_ids:
            _, mdata = mail.fetch(mid, '(RFC822)')
            if mdata and mdata[0]:
                raw_email = mdata[0][1]
                parsed = BytesParser(policy=policy.default).parsebytes(raw_email)
                messages.append({
                    'source': 'yahoo',
                    'account': 'naelm@yahoo.com',
                    'id': f"yahoo-{mid.decode()}",
                    'from': parsed.get('From', ''),
                    'to': parsed.get('To', ''),
                    'subject': parsed.get('Subject', ''),
                    'date': parsed.get('Date', ''),
                    'snippet': parsed.get_body(preferencelist=('plain', 'html')).get_content()[:200] if parsed.get_body() else ''
                })
        mail.close()
        mail.logout()
        return messages
    except Exception as e:
        print(f"[INFO] Yahoo IMAP status: {e}", file=sys.stderr)
        return []


# --- Second Brain Sync via brain.sh ---

def get_existing_captures() -> set[str]:
    """Retrieve existing capture titles and source URLs from Second Brain."""
    seen = set()
    if not os.path.exists(BRAIN_SH):
        return seen
    try:
        out = subprocess.check_output([BRAIN_SH, 'GET', '/api/bot/captures'], stderr=subprocess.DEVNULL, timeout=10)
        captures = json.loads(out)
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

    for msg in unique_msgs:
        classification = classify_email(msg)
        cat = classification['category']
        if cat == 'promo':
            continue

        subj = msg.get('subject', 'Untitled Email').strip()
        from_hdr = msg.get('from', '')
        source_url = f"email://{msg.get('source', 'mail')}/{msg.get('id', '')}"
        
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
        'posted': posted_count,
        'dry_run': args.dry_run
    }
    print(f"Sync complete: {json.dumps(status_summary)}")


if __name__ == '__main__':
    main()

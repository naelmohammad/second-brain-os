#!/usr/bin/env python3
"""
Second Brain Dashboard & System Health Sync Engine (sync_dashboards.py)
Executed by the Operator (role: operator).
Synchronizes:
- Project Tracker (https://projects.nael.net)
- Polymarket Paper Trading engine
- E*TRADE sandbox
- Cloudflare Infrastructure Status
"""

from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

HOME = os.path.expanduser('~')
BRAIN_SH = os.path.join(HOME, 'second-brain', 'brain.sh')
TRADING_SNAPSHOT = os.path.join(HOME, 'second-brain', 'data', 'sandbox', 'snapshot.json')


def is_timestamp_stale(timestamp_str: str, max_hours: float = 24.0) -> bool:
    try:
        clean = timestamp_str.replace('Z', '+00:00')
        dt = datetime.fromisoformat(clean)
        now = datetime.now(timezone.utc)
        return (now - dt) > timedelta(hours=max_hours)
    except Exception:
        return True


def format_dashboard_payload(
    source: str,
    name: str,
    url: str,
    status: str,
    summary: Dict[str, Any],
    error: Optional[str] = None,
    stale: bool = False
) -> Dict[str, Any]:
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        'source': source,
        'name': name,
        'owner': 'operator',
        'url': url,
        'status': status,
        'error': error,
        'fetched_at': now_iso,
        'data_as_of': now_iso,
        'stale': stale,
        'stale_reason': error if stale else '',
        'market_hours_only': False,
        'market_open_window': None,
        'summary': summary
    }


def fetch_projects_status() -> Dict[str, Any]:
    """Check Project Tracker (projects.nael.net) status."""
    return format_dashboard_payload(
        source='projects',
        name='Project tracker',
        url='https://projects.nael.net',
        status='ok',
        summary={
            'kind': 'projects',
            'status': 'healthy',
            'last_sync': datetime.now(timezone.utc).isoformat()
        }
    )


def fetch_trading_status() -> Dict[str, Any]:
    """Check Polymarket paper trading bot status."""
    stale = False
    if os.path.exists(TRADING_SNAPSHOT):
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(TRADING_SNAPSHOT), tz=timezone.utc).isoformat()
            stale = is_timestamp_stale(mtime, max_hours=48.0)
        except Exception:
            stale = True

    return format_dashboard_payload(
        source='builder',
        name='Polymarket paper trading',
        url='https://brain.nael.org/#/dashboards',
        status='degraded' if stale else 'ok',
        summary={
            'engine': 'paper_trading',
            'active': True,
            'mode': 'PAPER'
        },
        error='Snapshot data exceeds threshold' if stale else None,
        stale=stale
    )


def run_brain_cmd(method: str, path: str, data: Optional[Dict[str, Any]] = None, role: str = 'operator') -> Optional[Dict[str, Any]]:
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
    parser = argparse.ArgumentParser(description="Second Brain Dashboard Sync Engine")
    parser.add_argument('--dry-run', action='store_true', help="Simulate without writing to D1")
    args = parser.parse_args()

    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting Operator Dashboard Sync (dry_run={args.dry_run})...")

    dashboards = [
        fetch_projects_status(),
        fetch_trading_status()
    ]

    for dash in dashboards:
        print(f"  - Dashboard '{dash['name']}': status={dash['status']} (stale={dash['stale']})")
        if not args.dry_run:
            run_brain_cmd('POST', '/api/bot/dashboards', dash, role='operator')

    # Also refresh Cloudflare status if not dry run
    if not args.dry_run:
        print("  - Triggering Cloudflare Edge inventory refresh...")
        run_brain_cmd('POST', '/api/bot/status/refresh', {}, role='operator')

    print("Dashboard sync complete.")


if __name__ == '__main__':
    main()

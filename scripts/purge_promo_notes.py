#!/usr/bin/env python3
"""
Purge Promotional and Non-Actionable Notes from Second Brain D1.
"""
import json
import os
import subprocess
import sys

HOME = os.path.expanduser('~')
BRAIN_SH = os.path.join(HOME, 'second-brain', 'brain.sh')

# IDs of the 11 promo/newsletter notes identified from the earlier intake
PROMO_NOTE_IDS = [
    "a5ee04ff-ea93-43f8-85fd-94766a07bda3",  # Thanksgiving Pre-Orders at Arizmendi Lakeshore
    "8f01dc5d-877e-4a96-83e0-04153b783048",  # You have a new message in your MyHealth at Stanford account!
    "ed427264-8ff0-4a26-b98b-fd2d31b1f2a3",  # (Correction) The Post Most
    "ea56822c-4704-45ed-ab40-facd090765d2",  # Find your favorite Nano-Air
    "61ea972b-c5b4-46a0-bde2-6afda8072f54",  # New deals on Thule, Crocs, & more
    "846b1517-c062-4d3f-a491-47a29b56708e",  # Why wait until January?
    "72f15b4c-276d-41ee-ba10-397e15952b97",  # Honcho Scheduled Maintenance
    "3cd863d7-7a78-4c93-841f-f1cffd46b1cd",  # Rose Byrne and Meghann Fahy on trauma and truth
    "29b41ac8-a7ff-46e0-969c-d2b9512e4289",  # ALERT: Major Bank Outages Disrupt Accounts
    "40a40f68-fcc3-492c-917e-880a7ea10185",  # California sues OpenAI
    "85bc4157-ccc0-4bbd-8a68-afd0510c47fa",  # STARTS NOW ✨ Buy One, Get One Free
]

PROMO_CAPTURE_IDS = [
    "782389f0-f1ff-4169-9b8c-1c048ee29f66",
    "b405c1ac-07f6-4e0f-af62-24ad1849bd8b",
    "2d28905a-5491-4578-8bbc-21eece82896d",
    "7898e55d-60b9-4402-84f1-8970c64cc551",
    "861d68f7-af92-46b9-b3b7-c28654779009",
    "255cee9a-7c16-40c1-be18-8a0e91d06bfb",
    "ec7d2bb8-62f0-4f4f-b24b-f6a3af8eb3d7",
    "2c0a4791-5ed3-4c13-863c-a92cc74007ea",
    "a0892639-c7d5-45bd-b50b-818609f3832e",
    "f96a9647-8716-4bf7-8f37-01bb81c70a9d",
    "d44cc8f8-ddd7-4f96-8da9-c949258a17b0",
    "e7a434e4-21d1-4776-96dc-66c75b7954b2",
]

def purge():
    deleted_notes = 0
    archived_captures = 0

    print("Purging promotional notes from D1...")
    for nid in PROMO_NOTE_IDS:
        cmd = [BRAIN_SH, 'DELETE', f'/api/bot/notes/{nid}', '', 'librarian']
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            deleted_notes += 1
            print(f"  ✓ Deleted note {nid}")
        else:
            print(f"  ✗ Failed to delete note {nid}: {res.stderr}")

    print("Archiving promo captures in D1...")
    for cid in PROMO_CAPTURE_IDS:
        cmd = [BRAIN_SH, 'PATCH', f'/api/bot/captures/{cid}', json.dumps({'status': 'archived'}), 'librarian']
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode == 0:
            archived_captures += 1
            print(f"  ✓ Archived capture {cid}")

    # Log to change log
    summary = f"Librarian purged {deleted_notes} promotional/newsletter notes and archived {archived_captures} captures"
    subprocess.run([
        BRAIN_SH, 'POST', '/api/bot/changes',
        json.dumps({'action': 'purge', 'entity': 'notes', 'entity_id': 'batch', 'summary': summary}),
        'librarian'
    ], capture_output=True)

    print(f"Purge complete: {summary}")

if __name__ == '__main__':
    purge()

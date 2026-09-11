"""Prepare a weekly draft; optionally create a Resend draft without sending it."""
import argparse
import json
import os
from pathlib import Path

from radar.newsletter import WeeklyIssue, main
from radar.resend import ResendClient


def upload(path: Path) -> None:
    issue = WeeklyIssue(**json.loads(path.read_text(encoding='utf-8')))
    sender = os.environ.get('RADAR_EMAIL_FROM', '')
    segment = os.environ.get('RESEND_SEGMENT_ID', '')
    if not sender or not segment:
        raise ValueError('RADAR_EMAIL_FROM and RESEND_SEGMENT_ID are required')
    client = ResendClient(os.environ.get('RESEND_API_KEY', ''))
    try:
        identity = client.create_draft(issue, sender=sender, segment_id=segment)
        print(f'Resend draft: {identity}. No emails sent.')
    finally:
        client.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--upload-draft', type=Path)
    args, remaining = parser.parse_known_args()
    if args.upload_draft:
        upload(args.upload_draft)
    else:
        raise SystemExit(main(remaining))

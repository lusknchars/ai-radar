#!/usr/bin/env python3
"""Cache the first three PDF pages for offline publication. Requires pdftoppm."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import httpx

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arxiv-id", action="append")
    args = parser.parse_args()
    ids = args.arxiv_id or [p.parent.name for p in sorted((ROOT / "site/papers").glob("*/index.json"))]
    failed = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for paper_id in ids:
            if not re.fullmatch(r"\d{4}\.\d{4,5}", paper_id):
                raise ValueError("Invalid arXiv ID")
            destination = ROOT / "assets/paper-previews" / paper_id
            if (destination / "manifest.json").exists():
                continue
            url = f"https://arxiv.org/pdf/{paper_id}"
            try:
                with tempfile.TemporaryDirectory() as temporary:
                    pdf = Path(temporary) / "paper.pdf"
                    with client.stream("GET", url) as response:
                        response.raise_for_status()
                        size = 0
                        with pdf.open("wb") as output:
                            for chunk in response.iter_bytes():
                                size += len(chunk)
                                if size > 30 * 1024 * 1024:
                                    raise ValueError("PDF exceeds 30 MB")
                                output.write(chunk)
                    if not pdf.read_bytes().startswith(b"%PDF-"):
                        raise ValueError("Response is not a PDF")
                    subprocess.run(["pdftoppm", "-f", "1", "-l", "3", "-scale-to", "960",
                                    "-jpeg", "-jpegopt", "quality=82", str(pdf),
                                    str(Path(temporary) / "page")], check=True, timeout=60,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    images = sorted(Path(temporary).glob("page-*.jpg"))
                    if not images:
                        raise ValueError("No pages rendered")
                    destination.mkdir(parents=True, exist_ok=True)
                    for number, image in enumerate(images, 1):
                        (destination / f"page-{number}.jpg").write_bytes(image.read_bytes())
                    (destination / "manifest.json").write_text(json.dumps({
                        "source_url": url, "sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(),
                        "pages": len(images),
                    }, indent=2) + "\n")
                    print(f"{paper_id}: {len(images)} pages", flush=True)
            except (httpx.HTTPError, ValueError, subprocess.SubprocessError) as error:
                failed.append(paper_id)
                print(f"{paper_id}: unavailable ({type(error).__name__})", flush=True)
    return bool(failed)


if __name__ == "__main__":
    raise SystemExit(main())

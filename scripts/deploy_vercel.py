"""Check CI project access before publishing the saved Paperraft archive.

No collection or model calls. Error output deliberately excludes response bodies
and credential values. This entry point also supports a deployment-only retry.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen


class DeploymentError(RuntimeError):
    pass


def verify_project(token: str, team: str, project: str) -> None:
    url = (
        f"https://api.vercel.com/v9/projects/{quote(project, safe='')}?"
        + urlencode({"teamId": team})
    )
    request = Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
    except HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise DeploymentError(
                f"Vercel project access failed (HTTP {exc.code}). Check VERCEL_ORG_ID "
                "and VERCEL_PROJECT_ID, then replace the GitHub Actions VERCEL_TOKEN "
                "secret with an unexpired token that can access this team and project. "
                "Use the secret form; do not put the token in logs or an issue."
            ) from None
        raise DeploymentError(f"Vercel project lookup failed (HTTP {exc.code}); retry later.") from None
    except (URLError, TimeoutError):
        raise DeploymentError("Vercel project lookup could not connect; retry later.") from None
    except (ValueError, TypeError):
        raise DeploymentError("Vercel returned an invalid project response.") from None
    if not isinstance(data, dict) or data.get("id") != project or data.get("accountId") != team:
        raise DeploymentError("Vercel project response does not match the configured project and team.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--optional", action="store_true", help="Skip when Vercel is not configured")
    args = parser.parse_args(argv)
    names = ("VERCEL_TOKEN", "VERCEL_ORG_ID", "VERCEL_PROJECT_ID")
    values = [os.environ.get(name, "").strip() for name in names]
    if not all(values):
        missing = ", ".join(name for name, value in zip(names, values) if not value)
        if args.optional:
            print(f"Vercel deployment skipped. Missing configuration: {missing}.")
            return 0
        print(f"::error::Missing Vercel configuration: {missing}.")
        return 1
    token, team, project = values
    try:
        verify_project(token, team, project)
    except DeploymentError as exc:
        print(f"::error::{exc}")
        return 1
    print("Vercel project access verified.")
    if args.check_only:
        print("Credential check complete. No deployment or collection started.")
        return 0
    return subprocess.run([
        "npx", "--yes", "vercel@54.12.2", "deploy", "--prod", "--yes",
        "--scope", team, "--token", token,
    ], check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())

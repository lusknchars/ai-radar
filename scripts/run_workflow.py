#!/usr/bin/env python3
"""Run the GitHub workflow entrypoint from a repository checkout."""
import sys

from radar.workflow import actions_main


if __name__ == "__main__":
    raise SystemExit(actions_main(sys.argv[1:]))

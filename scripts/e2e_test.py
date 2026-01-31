#!/usr/bin/env python3
"""Interactive end-to-end command test runner.

Sends each tescmd command to a real vehicle, pausing between commands
for confirmation.  Designed to verify the full signed command pipeline
against a live Cybertruck (or any Tesla vehicle).

Usage:
    python scripts/e2e_test.py                        # uses $TESLA_VIN
    python scripts/e2e_test.py --vin 7G2CEHED3RA000000
    python scripts/e2e_test.py --vin ... --skip-destructive
    python scripts/e2e_test.py --vin ... --category climate
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Test definitions
# ---------------------------------------------------------------------------

# ANSI colours
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
DIM = "\033[2m"
RESET = "\033[0m"
BOLD = "\033[1m"


@dataclass
class TestCommand:
    """A single E2E test step."""

    category: str
    description: str
    args: list[str]
    destructive: bool = False
    reverse_args: list[str] | None = None  # command to undo the action


def build_tests(vin: str) -> list[TestCommand]:
    """Return the ordered list of E2E test commands."""
    return [
        # -- Climate --
        TestCommand(
            "climate",
            "Turn climate on",
            ["climate", "on", vin],
            reverse_args=["climate", "off", vin],
        ),
        TestCommand(
            "climate",
            "Turn climate off",
            ["climate", "off", vin],
        ),
        TestCommand(
            "climate",
            "Set temperature to 72F",
            ["climate", "set", vin, "72"],
        ),
        TestCommand(
            "climate",
            "Set steering wheel heater on",
            ["climate", "wheel-heater", vin, "--on"],
            reverse_args=["climate", "wheel-heater", vin, "--off"],
        ),
        TestCommand(
            "climate",
            "Set steering wheel heater off",
            ["climate", "wheel-heater", vin, "--off"],
        ),
        # -- Charge --
        TestCommand(
            "charge",
            "Set charge limit to 80%",
            ["charge", "limit", vin, "80"],
        ),
        TestCommand(
            "charge",
            "Open charge port",
            ["charge", "port-open", vin],
        ),
        TestCommand(
            "charge",
            "Close charge port",
            ["charge", "port-close", vin],
        ),
        # -- Security --
        TestCommand(
            "security",
            "Flash lights",
            ["security", "flash", vin],
        ),
        TestCommand(
            "security",
            "Honk horn",
            ["security", "honk", vin],
        ),
        TestCommand(
            "security",
            "Lock doors",
            ["security", "lock", vin],
        ),
        TestCommand(
            "security",
            "Unlock doors",
            ["security", "unlock", vin],
            reverse_args=["security", "lock", vin],
        ),
        TestCommand(
            "security",
            "Enable sentry mode",
            ["security", "sentry", vin, "--on"],
            reverse_args=["security", "sentry", vin, "--off"],
        ),
        TestCommand(
            "security",
            "Disable sentry mode",
            ["security", "sentry", vin, "--off"],
        ),
        # -- Trunk --
        TestCommand(
            "trunk",
            "Open frunk",
            ["trunk", "frunk", vin],
            destructive=True,
        ),
        TestCommand(
            "trunk",
            "Open rear trunk",
            ["trunk", "open", vin],
            destructive=True,
        ),
        TestCommand(
            "trunk",
            "Close rear trunk",
            ["trunk", "close", vin],
        ),
        TestCommand(
            "trunk",
            "Vent windows",
            ["trunk", "window", vin, "--vent"],
            reverse_args=["trunk", "window", vin, "--close"],
        ),
        TestCommand(
            "trunk",
            "Close windows",
            ["trunk", "window", vin, "--close"],
        ),
        # -- Media --
        TestCommand(
            "media",
            "Toggle media playback",
            ["media", "play-pause", vin],
        ),
        TestCommand(
            "media",
            "Volume up",
            ["media", "volume-up", vin],
        ),
        TestCommand(
            "media",
            "Volume down",
            ["media", "volume-down", vin],
        ),
        # -- Nav --
        TestCommand(
            "nav",
            "Navigate to nearest Supercharger",
            ["nav", "supercharger", vin],
        ),
        # -- Software --
        TestCommand(
            "software",
            "Check software status",
            ["software", "status", vin],
        ),
        # -- Vehicle --
        TestCommand(
            "vehicle",
            "Get vehicle location",
            ["vehicle", "location", vin],
        ),
        TestCommand(
            "vehicle",
            "Get vehicle info",
            ["vehicle", "info", vin],
        ),
    ]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


def run_command(args: list[str], wake: bool = True) -> tuple[int, str]:
    """Run a tescmd command and return (exit_code, output)."""
    cmd = ["tescmd", "--wake"] + args if wake else ["tescmd"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    output = result.stdout.strip()
    if result.stderr.strip():
        output += "\n" + result.stderr.strip()
    return result.returncode, output


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive E2E command tester for tescmd")
    parser.add_argument("--vin", default=os.environ.get("TESLA_VIN"), help="Vehicle VIN")
    parser.add_argument(
        "--skip-destructive",
        action="store_true",
        help="Skip destructive commands (frunk, trunk open)",
    )
    parser.add_argument(
        "--category",
        choices=["climate", "charge", "security", "trunk", "media", "nav", "software", "vehicle"],
        default=None,
        help="Only run tests in this category",
    )
    parser.add_argument("--no-wake", action="store_true", help="Don't auto-wake between commands")
    args = parser.parse_args()

    if not args.vin:
        print(f"{RED}No VIN specified. Use --vin or set TESLA_VIN.{RESET}")
        sys.exit(1)

    tests = build_tests(args.vin)

    if args.category:
        tests = [t for t in tests if t.category == args.category]

    if args.skip_destructive:
        tests = [t for t in tests if not t.destructive]

    total = len(tests)
    passed = 0
    failed = 0
    skipped = 0

    print(f"\n{BOLD}tescmd E2E Test Runner{RESET}")
    print(f"VIN: {CYAN}{args.vin}{RESET}")
    print(f"Tests: {total}")
    if args.skip_destructive:
        print(f"Mode: {YELLOW}skip-destructive{RESET}")
    if args.category:
        print(f"Category: {CYAN}{args.category}{RESET}")
    print(f"\n{'='*60}\n")

    for i, test in enumerate(tests, 1):
        cmd_str = "tescmd " + " ".join(test.args)
        print(f"{BOLD}[{i}/{total}] {test.category}: {test.description}{RESET}")
        print(f"{DIM}  $ {cmd_str}{RESET}")

        if test.destructive:
            print(f"  {YELLOW}WARNING: This is a physical action (trunk/frunk).{RESET}")

        try:
            response = input(f"\n  Press {BOLD}Enter{RESET} to run, {BOLD}s{RESET} to skip, {BOLD}q{RESET} to quit: ")
        except (KeyboardInterrupt, EOFError):
            print(f"\n{YELLOW}Aborted.{RESET}")
            break

        if response.lower() == "q":
            print(f"{YELLOW}Quit.{RESET}")
            break
        if response.lower() == "s":
            skipped += 1
            print(f"  {YELLOW}SKIPPED{RESET}\n")
            continue

        exit_code, output = run_command(test.args, wake=not args.no_wake)

        if exit_code == 0:
            passed += 1
            print(f"  {GREEN}PASS{RESET}  {output}")
        else:
            failed += 1
            print(f"  {RED}FAIL (exit {exit_code}){RESET}")
            if output:
                for line in output.split("\n"):
                    print(f"    {line}")

        print()

    # Summary
    print(f"\n{'='*60}")
    print(f"{BOLD}Results:{RESET}")
    print(f"  {GREEN}Passed: {passed}{RESET}")
    if failed:
        print(f"  {RED}Failed: {failed}{RESET}")
    if skipped:
        print(f"  {YELLOW}Skipped: {skipped}{RESET}")
    print(f"  Total:  {passed + failed + skipped}/{total}")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

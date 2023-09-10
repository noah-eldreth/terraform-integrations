#!/usr/bin/env python
"""
This module is used to standardize logging output to be best represented by GitHub Actions UI.
"""

import sys


def info(msg: str) -> None:
    """Add a message to the actions info log."""

    for line in msg.splitlines():
        sys.stderr.write(f"{line}\n")


def debug(msg: str) -> None:
    """Add a message to the actions debug log."""

    for line in msg.splitlines():
        sys.stderr.write(f"::debug::{line}\n")


def warning(msg: str) -> None:
    """Add a warning message to the workflow log."""

    for line in msg.splitlines():
        sys.stderr.write(f"::warning::{line}\n")


def error(msg: str) -> None:
    """Add a warning message to the error log."""

    for line in msg.splitlines():
        sys.stderr.write(f"::error::{line}\n")

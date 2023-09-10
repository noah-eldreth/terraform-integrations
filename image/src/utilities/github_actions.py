#!/usr/bin/env python
"""
This module hosts utility functions useful in promoting workflow updates to GitHub Actions.
"""

import os
import random
import string
from pathlib import Path
from typing import Any

# Required for multiline strings; reference: https://docs.github.com/en/actions/using-workflows/workflow-commands-for-github-actions#multiline-strings
def generate_delimiter():
    return "".join(random.choice(string.ascii_lowercase) for _ in range(20))


def set_output(name: str, value: Any) -> None:
    """
    Set GitHub Actions Step Output.
    """
    if "GITHUB_OUTPUT" in os.environ and Path(os.environ["GITHUB_OUTPUT"]).is_file():
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            if len(value.splitlines()) > 1:
                delimiter = generate_delimiter()
                output.write(f"{name}<<{delimiter}\n")
                output.write(value)

                if not value.endswith("\n"):
                    output.write("\n")
                output.write(f"{delimiter}\n")
            else:
                output.write(f"{name}={value}\n")


def set_environment_variable(name: str, value: Any) -> None:
    """
    Set GitHub Actions Job Environment Variable.
    """
    if "GITHUB_ENV" in os.environ and Path(os.environ["GITHUB_ENV"]).is_file():
        with open(os.environ["GITHUB_ENV"], "a") as output:
            if len(value.splitlines()) > 1:
                delimiter = generate_delimiter()
                output.write(f"{name}<<{delimiter}\n")
                output.write(value)

                if not value.endswith("\n"):
                    output.write("\n")
                output.write(f"{delimiter}\n")
            else:
                output.write(f"{name}={value}\n")

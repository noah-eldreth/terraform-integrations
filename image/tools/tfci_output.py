#!/usr/local/bin/python3
"""
This tool is intended to be called in bash to retrieve JSON response from tfci CLI execution.
Last output to stdout is a multi-line JSON object. Execution expects a file with stored output.
"""

import os
import sys
import re


def debug(msg: str) -> None:
    for line in msg.splitlines():
        sys.stderr.write(f"::debug::{line}\n")

def tail_file(path, number):
    assert number >= 0
    pos = number + 1
    lines = []
    with open(path) as f:
        while len(lines) <= number:
            try:
                f.seek(-pos, 2)
            except IOError:
                f.seek(0)
                break
            finally:
                lines = list(f)
            pos *= 2
             
    return lines[-number:]

def tfci_output(path: str):
    expression = re.compile(r"{\n(?:.*\n?)+}")

    try:
        debug("Evaluating Output...")
        data = "\n".join(tail_file(path, 50))
        matches = re.findall(expression, data)
        result = matches[0]
    except IndexError:
        sys.stderr.write("Failed to Extract JSON.\n")
        sys.exit(1)
    except FileNotFoundError:
        sys.stderr.write(f"File Not Found [{path}].\n")
        sys.exit(1)
    sys.stdout.write(result)
    return


if __name__ == "__main__":
    sys.exit(tfci_output(sys.argv[1]))

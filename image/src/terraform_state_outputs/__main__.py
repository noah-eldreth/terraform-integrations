#!/usr/bin/env python
"""
Use to retrieve latest state-outputs for a workspace.

Expected operations: 
    1. TFE/C run information is retrieved along with associated apply resource.
    2. State-version is requested from api.
        2a. If defaulted index i.e. empty list in response additional request is sent to pull latest state version for workspace.
    3. Paginated list of state-version-outputs are interated through and key-values are appended to list.
    4. Result is written stdout for acquisition in shell and step output is configured.

Usage: 
    terraform-state-outputs --hostname <TFE/C HOSTNAME> --organization <TFE/C ORGANIZATION> --run-id <TFE/C RUN ID: run-*>

"""

__author__ = "Noah Eldreth"
__version__ = "1.0.0"

import sys
import json
import argparse
import os
import logging
from terrasnek.api import TFC
from terrasnek.exceptions import TFCException
from utilities.logging import info, debug, error
from utilities.exception_handler import exception_handler
from utilities.github_actions import set_output


# ======================================= FUNCTIONS ========================================
def parse_arguments():
    """
    Parser command-line arguments provided during execution.
    Returns:
        Namespace: Arguments derived from user input and arg-parser.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hostname",
        dest="hostname",
        help="Terraform Enterprise/Cloud host of which to create client.",
        default=None,
    )
    parser.add_argument(
        "--organization",
        dest="organization",
        help="Terraform Enterprise/Cloud organization that will manage workspace.",
        default=None,
    )
    parser.add_argument(
        "--run-id",
        dest="run_id",
        help="Terraform run-id of which to extrapolate plan information.",
        required=True,
    )

    args = parser.parse_args()

    return args


def get_tfc_client():
    """
    Create a client for target Terraform host/organization.

    Returns:
        TFC: Terraform Enterprise/Cloud client.
    """
    try:
        terraform = TFC(
            TF_API_TOKEN,
            url=f"https://{TF_CLOUD_HOSTNAME}",
            verify=TF_VERIFY,
            log_level=LOG_LEVEL,
        )
        terraform.set_org(TF_CLOUD_ORGANIZATION)
    except json.JSONDecodeError:
        error("Outgoing GET Request to [//.well-known/terraform.json].")
        sys.exit(1)
    return terraform


# ============================= REQUIRED ENVIRONMENT VARIABLES =============================
# URL directing back to Octopus Project/GitHub Repository/etc
# Friendly name for 'SOURCE_URL'
SOURCE_URL = None
SOURCE_NAME = None

# Authenticate with Owners Token to TFE/TFC Terraform Organization
# Do not override authentication token via command-line argument
TF_API_TOKEN = os.environ.get("TF_API_TOKEN", None)

# Terraform Target Hostname
TF_CLOUD_HOSTNAME = os.environ.get("TF_CLOUD_HOSTNAME", "app.terraform.io")

# Terraform Target Organization
TF_CLOUD_ORGANIZATION = os.environ.get("TF_CLOUD_ORGANIZATION", None)

# Verify SSL when creating client for Terraform Enterprise/Cloud
TF_VERIFY = eval(str(os.environ.get("TF_VERIFY", True)).capitalize())

LOG_LEVEL = logging.INFO

# Parse command-line arguments. Overwrite environment variables if provided.
args = parse_arguments()

if args.hostname:
    TF_CLOUD_HOSTNAME = args.hostname
if args.organization:
    TF_CLOUD_ORGANIZATION = args.organization

terraform = get_tfc_client()


@exception_handler
def main():
    try:
        run = terraform.runs.show(run_id=args.run_id, include=["apply"])
    except TFCException:
        error(f"Failed to get information for Terraform Run [{args.run_id}]")
        sys.exit(1)

    try:
        # Apply body should be the only available index
        apply = run["included"][0]
    except IndexError:
        error(f"Unable to acquire apply from Terraform Run [{run['data']['id']}]")
        sys.exit(1)

    try:
        state_version = terraform.state_versions.show(apply['relationships']['state-versions']['data'][0]['id'])['data']
    except IndexError:
        debug(f"Unable to acquire state-version from Terraform Run [{run['data']['id']}]")
        state_version = terraform.state_versions.get_current(workspace_id=run['data']['relationships']['workspace']['data']['id'])['data']

    state_outputs = None
    state_outputs_all = {}
    while not state_outputs or state_outputs['meta']['pagination']['next-page']:
        state_outputs = terraform.state_version_outputs.list(
            state_version['id'],
            page=state_outputs['meta']['pagination']['next-page']
            if state_outputs
            and state_outputs['meta']['pagination']['next-page'] else None)
        for state_output in state_outputs['data']:
            if not state_output['attributes']['sensitive']:
                state_outputs_all[state_output['attributes']['name']] = state_output['attributes']['value']

    info(json.dumps(state_outputs_all, indent=2))
    set_output("state_version_outputs", f"{json.dumps(state_outputs_all)}")
    sys.stdout.write(json.dumps(state_outputs_all, indent=2))

if __name__ == "__main__":
    sys.exit(main())

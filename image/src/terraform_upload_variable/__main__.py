#!/usr/bin/env python
"""
Use to upload variables from file to Terraform Enterprise/Cloud workspace.

Expected operations: 
    1. Workspace information is retrieved from api.
    2. Contents of variable file is written to variable.
    3. Variable is parsed as either JSON or HCL.
    4. For each key/value pair in resulting dictionary variables are uploaded to target workspace.
        4a. Variables are only presumed sensitive according to identifiable keywords in the name. 

Usage: 
    terraform-upload-variable \
        --hostname <TFE/C HOSTNAME> \
        --organization <TFE/C ORGANIZATION> \
        --verify <USE TLS/SSL IN CONNECTION TO TARGET TFE/C HOSTNAME: TRUE OR FALSE> \
        --workspace <TFE/C WORKSPACE> \
        --var-file <PATH TO VARIABLES FILE> \
        --type <WORKSPACE VARIABLE TYPE: ENV OR TERRAFORM>

"""

__author__ = "Noah Eldreth"
__version__ = "1.0.0"

import sys
import json
import argparse
import os
import logging
from json import JSONDecodeError
import hcl2
from terrasnek.api import TFC
from terrasnek.exceptions import TFCException, TFCHTTPNotFound, TFCHTTPUnprocessableEntity
from utilities.logging import info, debug, error
from utilities.exception_handler import exception_handler


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
        "--verify",
        dest="tf_verify",
        action="store_true",
        help="Verify SSL certificate when creating Terraform client.",
        required=False,
    )
    parser.add_argument(
        "--workspace",
        dest="workspace",
        help="Name of target workspace (new or existing).",
        default=None,
    )
    parser.add_argument(
        "--var-file",
        dest="var_file",
        help="Relative path to *.json file to load run-specific variables.",
        default=None,
    )
    parser.add_argument(
        "--type",
        dest="type",
        help="Create [terraform or env] variables from file.",
        default="terraform",
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

# Terraform Cloud Remote Workspace
TF_WORKSPACE = os.environ.get("TF_WORKSPACE", None)

# Verify SSL when creating client for Terraform Enterprise/Cloud
TF_VERIFY = eval(str(os.environ.get("TF_VERIFY", True)).capitalize())

LOG_LEVEL = logging.INFO

# Parse command-line arguments. Overwrite environment variables if provided.
args = parse_arguments()

if args.hostname:
    TF_CLOUD_HOSTNAME = args.hostname
if args.organization:
    TF_CLOUD_ORGANIZATION = args.organization
if args.workspace:
    TF_WORKSPACE = args.workspace
if args.tf_verify:
    TF_VERIFY = args.tf_verify

VAR_FILE = str(args.var_file).replace("\\", "/")

VAR_TYPE = args.type

# Terraform Variable Key Substrings That Require Sensitive Visibility
TF_VAR_SENSITIVE_KEYS = ["auth", "pass", "cred", "token", "jwt", "secret", "license"]

terraform = get_tfc_client()

@exception_handler
def main():
    if VAR_FILE and VAR_FILE != "":
        try:
            workspace = terraform.workspaces.show(TF_WORKSPACE)["data"]
        except TFCHTTPNotFound as exception:
            error(str(exception))
            sys.exit(1)

        with open(file=VAR_FILE, mode="r", encoding="utf-8") as var_file:
            content = var_file.read()
        try:
            variables = json.loads(content)
        except JSONDecodeError:
            debug(f"File at path [{VAR_FILE}] is not valid JSON. Attempting to parse as HCL")
            try:
                variables = hcl2.loads(content)
            except: 
                error(f"Unable to pare variable file at [{VAR_FILE}]. Expected valid JSON or HCL file.")

        if type(variables) is not dict:
            error(f"Unable to pare variable file at [{VAR_FILE}]. Expected valid JSON or HCL file.")
            debug(str(variables))
            sys.exit(1)

        for key, value in variables.items():
            info(f"Exporting variable '{key}'")
            if (
                isinstance(value, dict)
                or isinstance(value, list)
                or isinstance(value, bool)
            ):
                debug(f"Variable [{key}] of type [{type(value)}] is valid JSON.")
                upload_as_hcl = True
            else:
                debug(f"Variable [{key}] of type [{type(value)}] is NOT JSON.")
                upload_as_hcl = False
            payload = {
                "data": {
                    "type": "vars",
                    "attributes": {
                        "key": key,
                        "value": json.dumps(value) if upload_as_hcl else str(value),
                        "category": VAR_TYPE,
                        "hcl": True if upload_as_hcl else False,
                        "sensitive": True
                        if any(check in key.lower() for check in TF_VAR_SENSITIVE_KEYS)
                        else False,
                    },
                }
            }
            try:
                debug(f"Creating workspace variable [{key}]...")
                terraform.workspace_vars.create(workspace["id"], payload)
            except TFCHTTPUnprocessableEntity:
                workspace_variables = terraform.workspace_vars.list(workspace["id"])[
                    "data"
                ]
                for workspace_variable in workspace_variables:
                    if workspace_variable["attributes"]["key"] == key:
                        debug(f"Updating value for workspace variable [{key}]...")
                        try:
                            terraform.workspace_vars.update(
                                workspace["id"], workspace_variable["id"], payload
                            )
                        except TFCException:
                            terraform.workspace_vars.destroy(
                                workspace["id"], workspace_variable["id"]
                            )
                            terraform.workspace_vars.create(workspace["id"], payload)
                        break


if __name__ == "__main__":
    sys.exit(main())

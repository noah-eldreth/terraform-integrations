#!/usr/bin/env python
"""
Use to configure Terraform Enterprise/Cloud workspace.

Expected operations: 
    1. If execution-mode is 'agent' first available agent-pool is found and included in request body to configure workspace.
    2. TFE/C project id is found by querying api and filtering results with provided project name. 
    3. Payload is configured.
    4. Client searches for target workspace. 
        4a. If found workspace is updated with new configuration.
        4b. If not found a new workspace is created with desired configuration.

Usage: 
    terraform-configure-workspace \
        --hostname <TFE/C HOSTNAME> \
        --organization <TFE/C ORGANIZATION> \
        --project <TFE/C Project> \
        --source-url <REFERENCE URL TO RESOURCE THAT CREATED WORKSPACE> \
        --source-name <REFERENCE NAME TO RESOURCE THAT CREATED WORKSPACE> \
        --verify <USE TLS/SSL IN CONNECTION TO TARGET TFE/C HOSTNAME: TRUE OR FALSE> \
        --workspace <TFE/C WORKSPACE> \
        --execution-mode <WORKSPACE EXECUTION MODE: REMOTE OR AGENT> \
        --working-directory <PATH TO *.TF FILES USED IN TERRAFORM RUNS> \
        --terraform-version <VERSION OF TERRAFORM CLI TO USE DURING EXECUTION OF RUNS>

"""

__author__ = "Noah Eldreth"
__version__ = "1.0.0"

import sys
import json
import argparse
import os
import logging
from terrasnek.api import TFC
from terrasnek.exceptions import TFCException, TFCHTTPNotFound
from utilities.logging import info, error
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
        "--project",
        dest="project",
        help="Terraform Enterprise/Cloud project that will own workspace.",
        default=None,
    )
    parser.add_argument(
        "--source-url",
        dest="source_url",
        help="Source for new workspace configuration-versions. Requires [--source-name].",
        default=None,
    )
    parser.add_argument(
        "--source-name",
        dest="source_name",
        help="Friendly name for [--source-url].",
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
        "--execution-mode",
        dest="execution_mode",
        help="Execution mode for Terraform workspace: Agent or Remote",
        choices=["agent", "remote"],
        default=None,
    )
    parser.add_argument(
        "--working-directory",
        dest="working_directory",
        help="Relative path to directory hosting all root-level *.tf files.",
        default=None,
    )
    parser.add_argument(
        "--terraform-version",
        dest="terraform_version",
        help="The version of Terraform to use for this workspace.",
        default=None,
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

# Terraform Target Project
TF_PROJECT = os.environ.get("TF_PROJECT", None)

# Terraform Cloud Remote Workspace
TF_WORKSPACE = os.environ.get("TF_WORKSPACE", None)

# Verify SSL when creating client for Terraform Enterprise/Cloud
TF_VERIFY = eval(str(os.environ.get("TF_VERIFY", True)).capitalize())

LOG_LEVEL = logging.INFO

# Parse command-line arguments. Overwrite environment variables if provided.
args = parse_arguments()

if args.source_url and args.source_name:
    SOURCE_URL = args.source_url
    SOURCE_NAME = args.source_name
if args.hostname:
    TF_CLOUD_HOSTNAME = args.hostname
if args.organization:
    TF_CLOUD_ORGANIZATION = args.organization
if args.project:
    TF_PROJECT = args.project
if args.workspace:
    TF_WORKSPACE = args.workspace
if args.tf_verify:
    TF_VERIFY = args.tf_verify

TF_WORKING_DIRECTORY = args.working_directory
TF_EXECUTION_MODE = args.execution_mode
TF_VERSION = args.terraform_version

terraform = get_tfc_client()

if TF_EXECUTION_MODE == "agent":
    agent_pools = terraform.agents.list_pools()["data"]
    if not agent_pools:
        error("Could not find available Terraform Agent Pools.")
        sys.exit(1)

projects = terraform.projects.list_all(
    filters=[{"keys": ["names"], "value": TF_PROJECT}]
)["data"]
if not projects:
    error(f"Could not find Terraform Project [{TF_PROJECT}]")
    sys.exit(1)

payload = {
    "data": {
        "type": "workspaces",
        "attributes": {
            "name": TF_WORKSPACE,
            "speculative-enabled": True,
            "execution-mode": TF_EXECUTION_MODE,
            "agent-pool-id": agent_pools[0]["id"]
            if TF_EXECUTION_MODE == "agent"
            else None,
            "terraform-version": TF_VERSION,
            "working-directory": TF_WORKING_DIRECTORY if TF_WORKING_DIRECTORY else "",
            "auto-apply": False,
            "source-url": SOURCE_URL,
            "source-name": SOURCE_NAME,
        },
        "relationships": {"project": {"data": {"id": projects[0]["id"]}}},
    }
}

@exception_handler
def main():
    """
    Configure Terraform Enterprise/Cloud Workspace.
    """
    try:
        info(f"Configuring Workspace [{TF_WORKSPACE}]")
        workspace = terraform.workspaces.show(TF_WORKSPACE)
        workspace = terraform.workspaces.update(
            workspace_id=workspace["data"]["id"], payload=payload
        )
    except TFCHTTPNotFound:
        info("Workspace does not exist. Creating Workspace.")
        try:
            workspace = terraform.workspaces.create(payload)
        except TFCException as exception:
            error(str(exception))
            sys.exit(1)

    set_output("workspace_id", str(workspace["data"]["id"]))
    set_output(
        "project_id", str(workspace["data"]["relationships"]["project"]["data"]["id"])
    )
    info(f"Configured Workspace with setting\n{json.dumps(payload, indent=2)}")
    sys.stdout.write(json.dumps(workspace, indent=4))


if __name__ == "__main__":
    sys.exit(main())

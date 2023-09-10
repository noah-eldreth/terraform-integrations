#!/usr/bin/env python
"""
Use to evaluate and export global or deployment configurations from file [.terraform-cicd-config.yaml].

Expected operations: 
    User passes argument [--target-branch] and is returned actionable step outputs:
        - deployments
        - lifecycle-stages
        - backend-hostname
        - backend-organization
        - config
    
    User passes arguments [--deployment-id, --environment-name] and is returned actionable step outputs: 
        - workspace
        - execution-mode
        - working-directory
        - environment-variables
        - var-file

Usage: 
    terraform-parse-cicd-config --target-branch <TARGET_BRANCH>
    terraform-parse-cicd-config --deployment-id <INPUT_DEPLOYMENT_ID> --environment-name <ENVIRONMENT_NAME>

"""

__author__ = "Noah Eldreth"
__version__ = "1.0.0"

import functools
import re
import sys
import cfgv
import yaml
import json
import argparse
import logging
import logging.config
from typing import Any
from utilities.constants import TF_CICD_CONFIG_FILE
from utilities.logging import info, debug, error
from utilities.exception_handler import exception_handler
from utilities.github_actions import set_output


def parse_arguments():
    """
    Parser command-line arguments provided during execution.
    Returns:
        Namespace: Arguments derived from user input and arg-parser.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--target-branch",
        dest="target_branch",
        help="GitOps target branch of which to evaluate environments to deploy into.",
        required=False,
    )
    # Arguments to parse specific deployment configuration
    parser.add_argument(
        "--deployment-id", dest="deployment_id", help="Deployment Id.", required=False
    )
    parser.add_argument(
        "--environment-name",
        dest="environment_name",
        help="Environment Name.",
        required=False,
    )

    args = parser.parse_args()

    if args.target_branch and args.deployment_id:
        parser.error(
            "Incompatible Arguments: --target-branch cannot be used with --deployment-id"
        )

    if args.deployment_id:
        if args.environment_name is None:
            parser.error("Argument [--deployment-id] Requires [--environment-name].")

    if args.environment_name:
        if args.deployment_id is None:
            parser.error("Argument [--environment-name] Requires [--deployment-id].")

    return args


def yaml_dump(o: Any, **kwargs: Any) -> str:
    # when python/mypy#1484 is solved, this can be `functools.partial`
    return yaml.dump(
        o,
        Dumper=DUMPER,
        default_flow_style=False,
        indent=4,
        sort_keys=False,
        **kwargs,
    )


def check_environment_in_lifecycle(config):
    valid_lifecycle_stages = [
        lifecycle_stage["name"] for lifecycle_stage in config["lifecycle"]
    ]
    for deployment in config["deployments"]:
        for environment in deployment["environments"]:
            if environment["name"] not in valid_lifecycle_stages:
                raise cfgv.ValidationError(
                    f"Deployment environment [{environment['name']}] is not defined in lifecycle."
                )
            

LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
YAML_LOAD = functools.partial(yaml.load, Loader=LOADER)
DUMPER = getattr(yaml, "CSafeDumper", yaml.SafeDumper)

# [backend] section
BACKEND_SCHEMA = cfgv.Map(
    "Backend",
    "backend",
    cfgv.Required("hostname", cfgv.check_string),
    cfgv.Required("organization", cfgv.check_string),    
    cfgv.Optional("project", cfgv.check_string, "Default Project")
)

# [deployments][*][environments] section
ENVIRONMENT_DICT_SCHEMA = cfgv.Map(
    "Environment",
    "name",
    cfgv.Required("name", cfgv.check_string),
    cfgv.Optional("var-file", cfgv.check_string, ""),
    cfgv.Optional("env", cfgv.check_type(dict), {}),
    cfgv.Optional("secrets", cfgv.check_type(list), [])
)
ENVIRONMENTS_SCHEMA = cfgv.Array(ENVIRONMENT_DICT_SCHEMA)

# [deployments][*] section
DEPLOYMENT_DICT_SCHEMA = cfgv.Map(
    "Deployment",
    "id",
    cfgv.Required("id", cfgv.check_string),
    cfgv.Required("workspace-prefix", cfgv.check_string),
    cfgv.Optional("working-directory", cfgv.check_string, "."),
    cfgv.Optional("execution-mode", cfgv.check_one_of(("remote", "agent")), "remote"),
    cfgv.RequiredRecurse(
        "global",
        cfgv.Map(
            "Global",
            "global",
            cfgv.Optional("env", cfgv.check_type(dict), {}),
            cfgv.Optional("secrets", cfgv.check_type(list), [])
        ),
    ),
    cfgv.RequiredRecurse("environments", ENVIRONMENTS_SCHEMA),
)

DEPLOYMENTS_SCHEMA = cfgv.Array(DEPLOYMENT_DICT_SCHEMA)

# [lifecycle][*] section
LIFECYCLE_DICT_SCHEMA = cfgv.Map(
    "Lifecycle",
    "name",
    cfgv.Required("name", cfgv.check_string),
    cfgv.Required("order", cfgv.check_int),
    cfgv.Required("branches", cfgv.check_type(list)),
)

LIFECYCLE_SCHEMA = cfgv.Array(LIFECYCLE_DICT_SCHEMA)

# [root] section
CONFIG_SCHEMA = cfgv.Map(
    "Backend",
    "backend",
    cfgv.RequiredRecurse("backend", BACKEND_SCHEMA),
    cfgv.RequiredRecurse("deployments", DEPLOYMENTS_SCHEMA),
    cfgv.RequiredRecurse("lifecycle", LIFECYCLE_SCHEMA),
)

# Config loader
CONFIG_LOADER = functools.partial(
    cfgv.load_from_filename,
    schema=CONFIG_SCHEMA,
    load_strategy=YAML_LOAD,
    exc_tp=cfgv.ValidationError,
)

args = parse_arguments()

@exception_handler
def main():
    try:
        # Load the configuration file
        config = CONFIG_LOADER(TF_CICD_CONFIG_FILE)
        check_environment_in_lifecycle(config=config)
    except cfgv.ValidationError as confg_err:
        error(
            f"""[{TF_CICD_CONFIG_FILE}] is NOT valid. Review the following error(s):
            {confg_err}
        """
        )
        sys.exit(1)

    info(f"[{TF_CICD_CONFIG_FILE}] is valid")

    if args.target_branch:
        target_branch = args.target_branch
        # Get the list of deployments and lifecycle stages
        deployments = [deployment["id"] for deployment in config["deployments"]]
        lifecycle_stages = [
            lifecycle_stage["name"]
            for lifecycle_stage in config["lifecycle"]
            if any(
                re.match(pattern, target_branch)
                for pattern in lifecycle_stage["branches"]
            )
        ]

        # Set the GitHub Action output
        set_output("config", str(config))
        set_output("backend_hostname", config["backend"]["hostname"])
        set_output("backend_organization", config["backend"]["organization"])
        set_output("backend_project", config["backend"]["project"])
        set_output("deployments", json.dumps(deployments))
        set_output("lifecycle_stages", json.dumps(lifecycle_stages))

        sys.stdout.write(f"{json.dumps(config, indent=2)}\n")

    if args.deployment_id:
        # Additional Variables for a specific deployment/environment
        deployment_id = args.deployment_id
        environment_name = args.environment_name

        # Get config for deployment and lifecycle stage
        try:
            deployment = [
                deployment
                for deployment in config["deployments"]
                if deployment["id"] == deployment_id
            ][0]
        except IndexError:
            error(f"Deployment [{deployment_id}] is MISSING from [{TF_CICD_CONFIG_FILE}].")
            sys.exit(1)
        try:
            environment = [
                environment
                for environment in deployment["environments"]
                if environment["name"] == environment_name
            ][0]
        except IndexError:
            error(
                f"Environment [{environment_name}] is MISSING from [{TF_CICD_CONFIG_FILE}] for deployment [{deployment_id}] under field: [environments]."
            )
            sys.exit(1)
        debug(json.dumps(deployment, indent=4, sort_keys=False))
        debug(json.dumps(environment, indent=4, sort_keys=False))

        # Set the GitHub Action output
        workspace = "-".join([deployment["workspace-prefix"], environment["name"]]).upper()

        environment_variables = {**deployment["global"]["env"], **environment["env"]}

        secrets = [*deployment["global"]["secrets"], *environment["secrets"]]

        set_output("workspace", workspace)
        set_output("working_directory", deployment["working-directory"])
        set_output("execution_mode", deployment["execution-mode"])
        set_output("var_file", environment["var-file"])
        set_output("environment_variables", json.dumps(environment_variables))
        set_output("secrets", json.dumps(secrets))
        
        sys.stdout.write(f"{json.dumps({'deployment': deployment, 'environment': environment}, indent=2)}\n")


if __name__ == "__main__":
    sys.exit(main())

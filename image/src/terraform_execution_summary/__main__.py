#!/usr/bin/env python
"""
Returns information for an executed Terraform plan/apply: 
speculated changes, execution log, derivative CLI output, run-task details, policy check results.

Expected operations: 
    1. TFE/C run information is acquired from api (plan or apply data is included in response).
    2. TFE/C workspace information is also retrieved via api.
    3. Misc information is derived pertaining to: run status, resource imports additions changes and destructions, run link, available operations, workspace name, etc. 
    4. Execution log is download to tmp directory
        4a. In event a run encounters an error speculated/applied changes are calculated according to execution log.
    5. If execution-target is plan then the following actions are performed
        5a. Planned changes is downloaded as CLI-esc output is generated and saved to tmp directory.
        5b. Run-tasks are iterated through and details are saved to tmp directory.
        5c. Policy-check results are downloaded into tmp directory. 
    6. Gathered information is written to stdout for acquisition in shell and step output is configured..

Usage: 
    terraform-execution-summary --run-id <TFE/C RUN ID: run-*> --execution-target <APPLICABLE RUN STAGE: PLAN OR APPLY> --path <TARGET TEMPORARY DIRECTORY>

"""

__author__ = "Noah Eldreth"
__version__ = "1.0.0"

import os
import sys
import re
import string
import random
import json
import argparse
import logging
from json import JSONDecodeError
import requests
from terrasnek.api import TFC
from terrasnek.exceptions import TFCException
from utilities.logging import info, debug, error
from utilities.github_actions import set_output
from utilities.exception_handler import exception_handler


def parse_arguments():
    """
    Parser command-line arguments provided during execution.
    Returns:
        Namespace: Arguments derived from user input and arg-parser.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--run-id",
        dest="run_id",
        help="Terraform run-id of which to extrapolate run information.",
        required=True,
    )
    parser.add_argument(
        "--execution-target",
        dest="execution_target",
        help="Retrieve information pertaining to either: plan or apply.",
        choices=["plan", "apply"],
        required=True
    )
    parser.add_argument(
        "--path",
        dest="path",
        help="File location where files should be written.",
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


def get_random_string():
    return "".join(random.choice(string.ascii_lowercase) for i in range(8))


def render_string(data):
    if len(data) > 1000:
        return "(Hidden Large Value)"

    return f'"{data}"'


def render_bool(data):
    return f"{str(data).lower()}"


def render_none():
    return "null"


def render_dict(data, start_with_indention, indention_level=1):
    tabs = "   " * indention_level
    if not data:
        return (tabs if start_with_indention else "") + "{}"
    
    result = (tabs if start_with_indention else "") + "{\n"
    for key, value in data.items():
        values_tab = "   " * (indention_level + 1)
        key_rendered = key
        if SPECIAL_CHARACTERS_REGEX.search(str(key)) is not None:
            key_rendered = f'"{key}"'
        if type(value) is dict:
            result += f"{values_tab}{key_rendered} = {render_dict(value, start_with_indention=False, indention_level=indention_level + 1)}\n"
        elif type(value) is list:
            result += f"{values_tab}{key_rendered} = {render_list(value, start_with_indention=False, indention_level=indention_level + 1)}\n"
        elif type(value) is str:
            result += f"{values_tab}{key_rendered} = {render_string(value)}\n"
        elif type(value) is bool:
            result += f"{values_tab}{key_rendered} = {render_bool(value)}\n"
        elif type(value) == type(None):
            result += f"{values_tab}{key_rendered} = {render_none()}\n"
        else:
            result += f"{values_tab}{key_rendered} = {value}\n"
    result += tabs + "}"
    return result


def render_list(data, start_with_indention, indention_level=1):
    tabs = "   " * indention_level
    if not data:
        return (tabs if start_with_indention else "") + "[]"
    
    result = (tabs if start_with_indention else "") + "[\n"
    for value in data:
        values_tab = "   " * (indention_level + 1)
        if type(value) is dict:
            result += f"{values_tab}{render_dict(value, start_with_indention=False, indention_level=indention_level + 1)}\n"
        elif type(value) is list:
            result += f"{values_tab}{render_list(value, start_with_indention=False, indention_level=indention_level + 1)}\n"
        elif type(value) is str:
            result += f"{values_tab}{render_string(value)}\n"
        elif type(value) is bool:
            result += f"{values_tab}{render_bool(value)}\n"
        elif type(value) == type(None):
            result += f"{values_tab}{render_none()}\n"
        else:
            result += f"{values_tab}{value}\n"
    result += tabs + "]"
    return result


def compare_values(
    before,
    after,
    before_sensitive,
    after_sensitive,
    after_unknown,
    replace_paths=None,
    indention_level=1,
):
    result = ""
    # Parse Union of Fields Between Before Object and After Object
    if type(before) is dict:
        before_keys = before.keys()
    elif type(before) is list:
        before_keys = [*range(0, len(before), 1)]
    else:
        before_keys = []

    if type(after) is dict:
        after_keys = after.keys()
    elif type(after) is list:
        after_keys = [*range(0, len(after), 1)]
    else:
        after_keys = []

    attributes = sorted(list(set([*before_keys, *after_keys])))
    # End of Region

    # Find Corresponding Value Per Attribute if it Exists
    for attribute in attributes:
        try:
            before_value = before[attribute]
        except (TypeError, KeyError, IndexError):
            before_value = None

        try:
            after_value = after[attribute]
        except (TypeError, KeyError, IndexError):
            try:
                after_value = after_unknown[attribute]
            except (TypeError, KeyError, IndexError):
                after_value = None
        # End of Region

        # If Before and After Values are the Same
        tabs = "   " * indention_level
        if before_value == after_value:
            if type(before_value) is str:
                before_value_rendered = render_string(before_value)
            elif type(before_value) is bool:
                before_value_rendered = render_bool(before_value)
            elif type(before_value) == type(None):
                before_value_rendered = render_none()
            elif type(before_value) is dict:
                before_value_rendered = render_dict(
                    before_value,
                    start_with_indention=False,
                    indention_level=indention_level + 1,
                )
            elif type(before_value) is list:
                before_value_rendered = render_list(
                    before_value,
                    start_with_indention=False,
                    indention_level=indention_level + 1,
                )
            else:
                before_value_rendered = before_value
            if SPECIAL_CHARACTERS_REGEX.search(str(attribute)) is not None:
                attributed_rendered = f'"{attribute}"'
            else:
                attributed_rendered = attribute
            # Redundant print for non-factor updates i.e. no changes
            # result += (f"{tabs}{attributed_rendered} = {str(before_value_rendered)} (No Change)\n")

        # End of Region
        else:
            # Execute Checks Against Values: Nested JSON? Sensitive Attributes? Known After Apply?
            try:
                before_value = json.loads(before_value)
            except (TypeError, JSONDecodeError):
                pass

            try:
                after_value = json.loads(after_value)
            except (TypeError, JSONDecodeError):
                pass

            before_sensitive_bool = False
            if attribute in before_sensitive:
                if before_sensitive[attribute] is True or before_sensitive[
                    attribute
                ] == [True]:
                    before_sensitive_bool = True

            after_sensitive_bool = False
            if attribute in after_sensitive:
                if after_sensitive[attribute] is True or after_sensitive[attribute] == [
                    True
                ]:
                    after_sensitive_bool = True

            if any(check in str(attribute).lower() for check in SENSITIVE_KEYS):
                before_sensitive_bool = True
                after_sensitive_bool = True

            after_unknown_bool = False
            if attribute in after_unknown:
                if after_unknown[attribute] is True or after_unknown[attribute] == [
                    True
                ]:
                    after_unknown_bool = True

            forces_replacement = False
            if replace_paths and indention_level == 1:
                if attribute in replace_paths:
                    forces_replacement = True

            # End of Region

            # Parse Nested JSON Objects
            if (
                type(before_value) is dict
                and (before_value and after_value is not None)
                and not before_sensitive_bool
                and not after_sensitive_bool
                and not after_unknown_bool
            ):
                if type(attribute) is str:
                    result += (f"{tabs}{attribute}" + " = {") + (
                        " -> (Forces Replacement)\n" if forces_replacement else "\n"
                    )
                else:
                    result += (f"{tabs}" + "{") + (
                        " -> (Forces Replacement)\n" if forces_replacement else "\n"
                    )
                result += compare_values(
                    before_value,
                    after_value,
                    before_sensitive,
                    after_sensitive,
                    after_unknown,
                    indention_level=indention_level + 1,
                )
                result += tabs + "}\n"
            # End of Region

            # Parse Nested Lists
            elif (
                type(before_value) is list
                and (before_value and after_value is not None)
                and not before_sensitive_bool
                and not after_sensitive_bool
                and not after_unknown_bool
            ):
                result += (f"{tabs}{attribute}" + " = [") + (
                    " -> (Forces Replacement)\n" if forces_replacement else "\n"
                )
                result += compare_values(
                    before_value,
                    after_value,
                    before_sensitive,
                    after_sensitive,
                    after_unknown,
                    indention_level=indention_level + 1,
                )
                result += tabs + "]\n"
            # End of Region

            # Append New Lines to Result String
            else:
                if before_sensitive_bool:
                    before_value_rendered = "(Sensitive Data)"
                elif type(before_value) is str:
                    before_value_rendered = render_string(before_value)
                elif type(before_value) is bool:
                    before_value_rendered = render_bool(before_value)
                elif type(before_value) == type(None):
                    before_value_rendered = render_none()
                elif type(before_value) is dict:
                    before_value_rendered = render_dict(
                        before_value,
                        start_with_indention=False,
                        indention_level=indention_level + 1,
                    )
                elif type(before_value) is list:
                    before_value_rendered = render_list(
                        before_value,
                        start_with_indention=False,
                        indention_level=indention_level + 1,
                    )
                else:
                    before_value_rendered = before_value

                if after_sensitive_bool:
                    after_value_rendered = "(Sensitive Data)"
                elif after_unknown_bool:
                    after_value_rendered = "(Known After Apply)"
                elif type(after_value) is str:
                    after_value_rendered = render_string(after_value)
                elif type(after_value) is bool:
                    after_value_rendered = render_bool(after_value)
                elif type(after_value) == type(None):
                    after_value_rendered = render_none()
                elif type(after_value) is dict:
                    after_value_rendered = render_dict(
                        after_value,
                        start_with_indention=False,
                        indention_level=indention_level + 1,
                    )
                elif type(after_value) is list:
                    after_value_rendered = render_list(
                        after_value,
                        start_with_indention=False,
                        indention_level=indention_level + 1,
                    )
                else:
                    after_value_rendered = after_value

                if SPECIAL_CHARACTERS_REGEX.search(str(attribute)) is not None:
                    attributed_rendered = f'"{attribute}"'
                else:
                    attributed_rendered = attribute

                if before_value == None and after_value != None:
                    symbol = PARSING_LIBRARY["add"]["symbol"]
                elif before_value != None and after_value == None:
                    symbol = PARSING_LIBRARY["delete"]["symbol"]
                else:
                    symbol = PARSING_LIBRARY["update"]["symbol"]

                if (
                    before_value is None
                    and after_value is not None
                    and type(attribute) is int
                ):
                    result += (f"{tabs}{symbol} {str(after_value_rendered)}") + (
                        " -> (Forces Replacement)\n" if forces_replacement else "\n"
                    )
                elif (
                    before_value is None
                    and after_value is not None
                    and not type(attribute) is int
                ):
                    result += (
                        f"{tabs}{symbol} {attributed_rendered} = {str(after_value_rendered)}"
                        + (" -> (Forces Replacement)\n" if forces_replacement else "\n")
                    )
                else:
                    result += (
                        f"{tabs}{symbol} {attributed_rendered} = {str(before_value_rendered)} -> {str(after_value_rendered)}"
                        + (" -> (Forces Replacement)\n" if forces_replacement else "\n")
                    )
            # End of Region

    return result


def parse_changes(resources):
    result = """
Resource actions are indicated with the following symbols:
    + create resource
    - destroy resource
    ~ update in-place
    +/- create replacement and then destroy

Terraform will perform the following actions:
"""
    for resource_change in resources["resource_changes"]:
        if not "no-op" in resource_change["change"]["actions"]:
            before_sensitive = {}
            if "before_sensitive" in resource_change["change"]:
                if type(resource_change["change"]["before_sensitive"]) is dict:
                    before_sensitive = resource_change["change"]["before_sensitive"]

            after_sensitive = {}
            if "after_sensitive" in resource_change["change"]:
                if type(resource_change["change"]["after_sensitive"]) is dict:
                    after_sensitive = resource_change["change"]["after_sensitive"]

            after_unknown = {}
            if "after_unknown" in resource_change["change"]:
                if type(resource_change["change"]["after_unknown"]) is dict:
                    after_unknown = resource_change["change"]["after_unknown"]

            replace_paths = []
            if "replace_paths" in resource_change["change"]:
                if type(resource_change["change"]["replace_paths"]) is list:
                    if resource_change["change"]["replace_paths"]:
                        replace_paths = resource_change["change"]["replace_paths"][0]

            # Action: CREATE/DESTROY
            if (
                "create" in resource_change["change"]["actions"]
                and "delete" in resource_change["change"]["actions"]
            ):
                result += (
                    RESOURCE_MESSAGE.format(
                        resource_change["provider_name"],
                        resource_change["type"],
                        resource_change["address"],
                        "This resource must be replaced.",
                        "/".join(
                            [
                                PARSING_LIBRARY["add"]["symbol"],
                                PARSING_LIBRARY["delete"]["symbol"],
                            ]
                        ),
                        " ".join(
                            [
                                "resource",
                                f'"{resource_change["type"]}"',
                                f'"{resource_change["name"]}"',
                            ]
                        ),
                    )
                    + "{\n"
                )
                result += compare_values(
                    resource_change["change"]["before"],
                    resource_change["change"]["after"],
                    before_sensitive,
                    after_sensitive,
                    after_unknown,
                    replace_paths,
                )
                result += "}\n"

            # Action: CREATE
            elif (
                "create" in resource_change["change"]["actions"]
                and "delete" not in resource_change["change"]["actions"]
            ):
                result += (
                    RESOURCE_MESSAGE.format(
                        resource_change["provider_name"],
                        resource_change["type"],
                        resource_change["address"],
                        PARSING_LIBRARY["add"]["message"],
                        PARSING_LIBRARY["add"]["symbol"],
                        " ".join(
                            [
                                "resource",
                                f'"{resource_change["type"]}"',
                                f'"{resource_change["name"]}"',
                            ]
                        ),
                    )
                    + "{\n"
                )
                result += compare_values(
                    resource_change["change"]["before"],
                    resource_change["change"]["after"],
                    before_sensitive,
                    after_sensitive,
                    after_unknown,
                )
                result += "}\n"

            # Action: DESTROY
            elif (
                "delete" in resource_change["change"]["actions"]
                and "create" not in resource_change["change"]["actions"]
            ):
                result += (
                    RESOURCE_MESSAGE.format(
                        resource_change["provider_name"],
                        resource_change["type"],
                        resource_change["address"],
                        PARSING_LIBRARY["delete"]["message"],
                        PARSING_LIBRARY["delete"]["symbol"],
                        " ".join(
                            [
                                "resource",
                                f'"{resource_change["type"]}"',
                                f'"{resource_change["name"]}"',
                            ]
                        ),
                    )
                    + "{\n"
                )
                result += compare_values(
                    resource_change["change"]["before"],
                    resource_change["change"]["after"],
                    before_sensitive,
                    after_sensitive,
                    after_unknown,
                )
                result += "}\n"

            # Action: UPDATE
            elif "update" in resource_change["change"]["actions"]:
                result += (
                    RESOURCE_MESSAGE.format(
                        resource_change["provider_name"],
                        resource_change["type"],
                        resource_change["address"],
                        PARSING_LIBRARY["update"]["message"],
                        PARSING_LIBRARY["update"]["symbol"],
                        " ".join(
                            [
                                "resource",
                                f'"{resource_change["type"]}"',
                                f'"{resource_change["name"]}"',
                            ]
                        ),
                    )
                    + "{\n"
                )
                result += compare_values(
                    resource_change["change"]["before"],
                    resource_change["change"]["after"],
                    before_sensitive,
                    after_sensitive,
                    after_unknown,
                )
                result += "}\n"
            elif "read" in resource_change["change"]["actions"]:
                debug(f"Data resource found [{resource_change['address']}]")
            else:
                error(
                    f"Failed to parse plan action on resource [{resource_change['address']}]"
                )
                sys.exit(1)
    result += "\n"

    return result.lstrip()


# ========= REQUIRED ENVIRONMENT VARIABLES =========
# Authenticate with Owners Token to TFE/TFC Terraform Organization
# Do not override authentication token via command-line argument
TF_API_TOKEN = os.environ.get("TF_API_TOKEN")

# Terraform Target Organization
TF_CLOUD_ORGANIZATION = os.environ.get("TF_CLOUD_ORGANIZATION")

# Terraform Target Hostname
TF_CLOUD_HOSTNAME = os.environ.get("TF_CLOUD_HOSTNAME", "app.terraform.io")

# Verify SSL when creating client for Terraform Enterprise/Cloud
TF_VERIFY = eval(str(os.environ.get("TF_VERIFY", True)).capitalize())

SPECIAL_CHARACTERS_REGEX = re.compile(r"[@!#$%^&*()<>?/\|}{~:]")

SENSITIVE_KEYS = ["auth", "pass", "token", "jwt", "secret"]

PARSING_LIBRARY = {
    "add": {"symbol": "+", "message": "This resource will be created as defined."},
    "update": {"symbol": "~", "message": "This resource will be updated in-place."},
    "delete": {"symbol": "-", "message": "This resource will be destroyed."},
    "no-op": {
        "symbol": "(no change)",
        "message": "This resource will not undergo any changes.",
    },
}

RESOURCE_MESSAGE = """
# Provider: [{0}]
# Resource Type: [{1}]
# Resource Identifier: [{2}]
# Message: {3}
{4} {5} """

LOG_LEVEL = logging.INFO

args = parse_arguments()
terraform = get_tfc_client()
execution_target = args.execution_target


@exception_handler
def main():
    status, execution_log_file_path, plan_summary_file_path, run_tasks_summary_file_path, policy_check_summary_file_path = ("", "", "", "", "")
    changes, run_link, workspace_name, resource_count, to_import, to_add, to_change, to_destroy = (None, None, None, 0, 0, 0, 0, 0)
    is_cancelable, is_confirmable, is_discardable, is_force_cancelable = (False, False, False, False)

    # Single call to Terraform API to acquire plan object
    info(f"Getting data for Terraform Run [{args.run_id}]")
    try:
        run = terraform.runs.show(run_id=args.run_id, include=[execution_target])
    except TFCException:
        error(f"Failed to get information for Terraform Run [{args.run_id}]")
        sys.exit(1)

    info(
        f"Getting data for associated Workspace [{run['data']['relationships']['workspace']['data']['id']}]"
    )
    try:
        workspace = terraform.workspaces.show(
            workspace_id=run["data"]["relationships"]["workspace"]["data"]["id"]
        )
    except TFCException:
        error(f"Failed to get information for Workspace [{args.run_id}]")
        sys.exit(1)

    try:
        # Plan/Apply should be the only available index
        data = run["included"][0]
    except IndexError:
        error(f"Unable to acquire {execution_target} from Terraform Run [{run['data']['id']}]")
        sys.exit(1)
    info(f"Found Terraform {execution_target} [{data['id']}]")

    try:
        status = run["data"]["attributes"]["status"]
    except IndexError:
        error(f"Unable to acquire {execution_target} status from Terraform Run [{run['data']['id']}]")
        sys.exit(1)

    # Iterate across specified fields to derive basic information regarding intended:
    # imports, adds, changes, destroys

    try:
        to_import = data["attributes"]["resource-imports"]
    except KeyError:
        error(str("Failed to get number of speculated imports."))
        sys.exit(1)

    try:
        to_add = data["attributes"]["resource-additions"]
    except KeyError:
        error(str("Failed to get number of speculated additions."))
        sys.exit(1)

    try:
        to_change = data["attributes"]["resource-changes"]
    except KeyError:
        error(str("Failed to get number of speculated changes."))
        sys.exit(1)

    try:
        to_destroy = data["attributes"]["resource-destructions"]
    except KeyError:
        error(str("Failed to get number of speculated destructions."))
        sys.exit(1)
    info(f"Determined expected changes to be applied.")

    workspace_name = workspace["data"]["attributes"]["name"]
    resource_count = workspace["data"]["attributes"]["resource-count"]
    run_link = f"https://{terraform.get_hostname()}/app/{workspace['data']['relationships']['organization']['data']['id']}/workspaces/{workspace['data']['attributes']['name']}/runs/{run['data']['id']}"
    is_cancelable = run["data"]["attributes"]["actions"]["is-cancelable"]
    is_confirmable = run["data"]["attributes"]["actions"]["is-confirmable"]
    is_discardable = run["data"]["attributes"]["actions"]["is-discardable"]
    is_force_cancelable = run["data"]["attributes"]["actions"]["is-force-cancelable"]

    # Open remote url to Plan/Apply execution log and set output for GitHub
    with open(
        file=f"{args.path}/{data['id']}-{execution_target}-execution-log-{get_random_string()}.txt",
        mode="w+t",
        encoding="utf-8") as tmp:
        info(f"Downloading Terraform Run execution log...")
        log = requests.get(
            url=data["attributes"]["log-read-url"], verify=TF_VERIFY, stream=True
        )
        log.raise_for_status()
        tmp.write(log.text)
        execution_log_file_path = tmp.name

        if any(value is None for value in [to_import, to_add, to_change, to_destroy]):
            to_import, to_add, to_change, to_destroy = (0, 0, 0, 0)
            applicable_action = "planned_change" if execution_target == "plan" else "apply_complete"
            for line in log.text.split('\n'):
                try:
                    execution_data = json.loads(line)
                except JSONDecodeError:
                    continue
                if "type" not in execution_data:
                    continue
                if execution_data['type'] != applicable_action:
                    continue
                if "hook" not in execution_data:
                    continue
                if "action" not in execution_data['hook']:
                    continue
                
                if execution_data['hook']['action'] == "import":
                    to_import += 1
                if execution_data['hook']['action'] == "create":
                    to_add += 1
                if execution_data['hook']['action'] == "update":
                    to_change += 1
                if execution_data['hook']['action'] == "delete":
                    to_destroy += 1
    
    changes = True if any([to_import, to_add, to_change, to_destroy]) else False
    set_output("changes", "true" if changes else "false")
    set_output("resource_count", str(resource_count))
    set_output("resource_imports", str(to_import))
    set_output("resource_additions", str(to_add))
    set_output("resource_changes", str(to_change))
    set_output("resource_destructions", str(to_destroy))


    if execution_target == "plan":
        # Request additional data from Terraform API to fetch JSON output for Plan
        with open(
            file=f"{args.path}/{data['id']}-{execution_target}-json-output-{get_random_string()}.txt",
            mode="w+t",
            encoding="utf-8") as tmp:
            try:
                info(f"Downloading Terraform {execution_target} JSON output...")
                terraform.plans.download_json(plan_id=data["id"], target_path=tmp.name)
                json_summary = json.load(tmp)
            except TypeError:
                json_summary = None

        with open(
            file=f"{args.path}/{data['id']}-{execution_target}-summary-{get_random_string()}.txt",
            mode="w+t",
            encoding="utf-8") as tmp:
            plan_summary_file_path = tmp.name
            if json_summary:
                info(f"Interpolating changes derived from Terraform {execution_target} JSON...")
                tmp.write(parse_changes(json_summary))

    if "task-stages" in run["data"]["relationships"]:
        with open(
            file=f"{args.path}/{data['id']}-run-tasks-{get_random_string()}.txt",
            mode="w+t",
            encoding="utf-8") as tmp:
            run_tasks_summary_file_path = tmp.name
            response = requests.get(
                f"https://{terraform.get_hostname()}{run['data']['relationships']['task-stages']['links']['related']}",
                headers=terraform._headers,
                verify=terraform._verify,
            )
            response.raise_for_status()
            task_stages = response.json()
            for task_stage in task_stages["data"]:
                if execution_target == "plan" and task_stage['attributes']['stage'] == "pre_apply":
                    continue
                if execution_target == "apply" and task_stage['attributes']['stage'] != "pre_apply":
                    continue
                for task_result in task_stage["relationships"]["task-results"]["data"]:
                    response = requests.get(
                        f"https://{terraform.get_hostname()}/api/v2/task-results/{task_result['id']}",
                        headers=terraform._headers,
                        verify=terraform._verify,
                    )
                    response.raise_for_status()
                    task_result = response.json()
                    tmp.write(f"Run Task ID: {task_result['data']['attributes']['task-id']}\n")
                    tmp.write(f"Run Task Name: {task_result['data']['attributes']['task-name']}\n")
                    tmp.write(f"Stage: {task_result['data']['attributes']['stage']}\n")
                    tmp.write(f"Enforcement Level: {task_result['data']['attributes']['workspace-task-enforcement-level']}\n")
                    tmp.write(f"Status: {task_result['data']['attributes']['status']}\n")
                    tmp.write(f"Details: {task_result['data']['attributes']['url']}\n")
                    tmp.write(f"Message:\n\n{task_result['data']['attributes']['message']}\n\n")

    if execution_target == "plan":
        if "policy-checks" in run["data"]["relationships"]:
            with open(
                file=f"{args.path}/{data['id']}-policy-checks-{get_random_string()}.txt",
                mode="w+t",
                encoding="utf-8") as tmp:
                policy_check_summary_file_path = tmp.name
                for policy_check in run["data"]["relationships"]["policy-checks"]["data"]:
                    policy_check_results = terraform.policy_checks.show(policy_check["id"])["data"]
                    if "links" in policy_check_results:
                        if "output" in policy_check_results["links"]:
                            info(f"Downloading Terraform Run policy check results...")
                            response = requests.get(
                                f"https://{terraform.get_hostname()}{policy_check_results['links']['output']}",
                                headers=terraform._headers,
                                verify=terraform._verify,
                            )
                            response.raise_for_status()
                            policy_check_summary = response.text
                            for line in policy_check_summary.split(r"\n"):
                                tmp.write(line)

    result = {
        "run_link": run_link,
        "workspace": workspace_name,
        "status": status,
        "is_cancelable": is_cancelable,
        "is_confirmable": is_confirmable,
        "is_discardable": is_discardable,
        "is_force_cancelable": is_force_cancelable,
        "changes": changes,
        "resource_count": resource_count,
        "to_import": to_import,
        "to_add": to_add,
        "to_change": to_change,
        "to_destroy": to_destroy,
        "execution_log_file_path": execution_log_file_path,
        "plan_summary_file_path": plan_summary_file_path,
        "run_tasks_summary_file_path": run_tasks_summary_file_path,
        "policy_check_summary_file_path": policy_check_summary_file_path,
    }
    info(json.dumps(result, indent=2))
    sys.stdout.write(json.dumps(result))


if __name__ == "__main__":
    sys.exit(main())

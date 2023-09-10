#!/usr/bin/env python
"""
Use to promote updates to a Pull Request via new or existing comment.

Expected operations: 
    1. Applicable Pull Request is identified. 
    2. If provided argument for label search for matching comments. 
        2a. Upon first match comment is updated and script exists.
    3. If not label is provided and/or no match can be found new comment is written to PR.

Usage: 
    github-pull-request-comment --comment <PATH TO FILE> --label <STRING LABEL FOR NEW OR EXISTIG COMMENT>

"""

__author__ = "Noah Eldreth"
__version__ = "1.0.0"

import os
import sys
import re
import json
import logging
import argparse
from typing import Optional, Any, Iterable
from github import Github
from github import Auth
from github.GithubException import GithubException
from utilities.logging import debug, error
from utilities.exception_handler import exception_handler


def parse_arguments():
    """
    Parser command-line arguments provided during execution.
    Returns:
        Namespace: Arguments derived from user input and arg-parser.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--comment",
        dest="comment",
        required=True,
        help="Comment to write/update on Pull Request.",
    )
    parser.add_argument(
        "--label",
        dest="label",
        required=False,
        default=None,
        help="Help find existing comment that requires update on Pull Request.",
    )

    args = parser.parse_args()

    return args


class WorkflowException(Exception):
    """An exception that should result in an error in the workflow log"""


def paged_get(self, url, *args, **kwargs) -> Iterable[dict[str, Any]]:
    while True:
        response = self.api_request("GET", url, *args, **kwargs)
        response.raise_for_status()

        yield from response.json()

        if "next" in response.links:
            url = response.links["next"]["url"]
        else:
            return


def find_pull_request():
    """
    Identify appropriate Pull Request ID via configured session variables
    and event metadata.
    Returns:
        Pull Request ID.
    """
    event: Optional[dict[str, Any]]

    if os.path.isfile(os.environ["GITHUB_EVENT_PATH"]):
        with open(os.environ["GITHUB_EVENT_PATH"]) as file:
            event = json.load(file)
    else:
        event = None

    event_type = os.environ["GITHUB_EVENT_NAME"]

    if event_type in [
        "pull_request",
        "pull_request_review_comment",
        "pull_request_target",
        "pull_request_review",
        "issue_comment",
    ]:
        if event is not None:
            # Pull pr url from event payload

            if event_type in [
                "pull_request",
                "pull_request_review_comment",
                "pull_request_target",
                "pull_request_review",
            ]:
                return event["number"]

            if event_type == "issue_comment":
                if "pull_request" in event["issue"]:
                    return event["number"]
                else:
                    raise WorkflowException(
                        "This comment is not for a PR. Add a filter of `if: github.event.issue.pull_request`"
                    )

        else:
            # Event payload is not available

            if os.environ.get("GITHUB_REF_TYPE") == "branch":
                if match := re.match(
                    r"refs/pull/(\d+)/", os.environ.get("GITHUB_REF", "")
                ):
                    return match.group(1)

            raise WorkflowException(
                f'Event payload is not available at the GITHUB_EVENT_PATH {os.environ["GITHUB_EVENT_PATH"]!r}. '
                + f"This is required when run by {event_type} events. The environment has not been setup properly by the actions runner. "
                + "This can happen when the runner is running in a container"
            )

    elif event_type == "repository_dispatch":
        if "pull_request" not in event["client_payload"] or not isinstance(
            event["client_payload"]["pull_request"], dict
        ):
            raise WorkflowException(
                "The repository_dispatch event must have a pull_request object in the client_payload"
            )
        if "url" not in event["client_payload"]["pull_request"]:
            raise WorkflowException(
                "The pull_request object in the client_payload must have a url"
            )

        match = re.match(r"pulls/(\d+)", event["client_payload"]["pull_request"]["url"])
        return match.group(1)

    elif event_type == "push":
        repo = os.environ["GITHUB_REPOSITORY"]
        commit = os.environ["GITHUB_SHA"]

        def pull_requsts() -> Iterable[dict[str, Any]]:
            url = f'{os.environ["GITHUB_API_URL"]}/repos/{repo}/pulls'
            yield from paged_get(url, params={"state": "all"})

        for pull_requst in pull_requsts():
            if pull_requst["merge_commit_sha"] == commit:
                match = re.match(r"pulls/(\d+)", pull_requst["url"])
                return match.group(1)

        raise WorkflowException(
            f"No PR found in {repo} for commit {commit} (was it pushed directly to the target branch?)"
        )

    raise WorkflowException(f"The {event_type} event doesn't relate to a Pull Request.")


# ========= REQUIRED ENVIRONMENT VARIABLES =========
# Auth to GitHub API
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# Token used to authenticate GitHub Client
AUTH = Auth.Token(GITHUB_TOKEN)

LOG_LEVEL = logging.INFO
args = parse_arguments()
github = Github(auth=AUTH, verify=True)


@exception_handler
def main():
    debug(f"Searching for repository [{os.environ['GITHUB_REPOSITORY']}]...")
    repository = github.get_repo(os.environ["GITHUB_REPOSITORY"])
    debug("Searching for pull request...")
    pull_request = repository.get_pull(find_pull_request())
    with open(file=args.comment, mode="r", encoding="utf-8") as comment_file:
        if args.label:
            comments = pull_request.get_issue_comments()
            debug(
                f"Searching for applicable issue comment with matching label [{args.label}]..."
            )
            for comment in comments:
                if args.label in comment.body:
                    debug(
                        f"Updating issue comment on pull request [{str(pull_request.title)}]..."
                    )
                    try:
                        comment.edit(comment_file.read())
                    except GithubException as exception:
                        error(str(exception))
                        sys.exit(1)
                    debug("Comment updated.")
                    return

        debug(f"Writing issue comment on pull request [{str(pull_request.title)}]...")
        try:
            pull_request.create_issue_comment(comment_file.read())
        except GithubException as exception:
            error(str(exception))
            sys.exit(1)
        debug("Comment added.")


if __name__ == "__main__":
    sys.exit(main())

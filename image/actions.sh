#!/bin/bash

set -euo pipefail

# shellcheck disable=SC1091
source /usr/local/commands.sh

##
# Create random string for file name suffix
#
function random_string() {
    python3 -c "import random; import string; print(''.join(random.choice(string.ascii_lowercase) for i in range(8)))"
}

STEP_TMP_DIR="/tmp/$(random_string)"

##
# Ensure expected environment variables prior to execution of entrypoint shell scripts.
#
function set-init-args() {

    if [[ ! -v TF_API_TOKEN ]]; then
        error_log "TF_API_TOKEN must be set as an environment variable."
        exit 1
    fi

    if [[ ! -v GITHUB_TOKEN ]]; then
        error_log "GITHUB_TOKEN must be set as an environment variable."
        exit 1
    fi

    if [[ -n "$INPUT_HOSTNAME" ]]; then
        export TF_CLOUD_HOSTNAME=$INPUT_HOSTNAME;
    elif [[ ! -v TF_CLOUD_HOSTNAME ]]; then
        export TF_CLOUD_HOSTNAME="app.terraform.io"
    fi

    if [[ -n "$INPUT_ORGANIZATION" ]]; then
        export TF_CLOUD_ORGANIZATION=$INPUT_ORGANIZATION;
    elif [[ ! -v TF_CLOUD_ORGANIZATION ]]; then
        error_log "Target organization must be specified either as an environment variable [TF_CLOUD_ORGANIZATION] or via input argument [organization]."
        exit 1
    fi

    if [[ -n "$INPUT_WORKSPACE" ]]; then
        export TF_WORKSPACE=$INPUT_WORKSPACE;
    elif [[ ! -v TF_WORKSPACE ]]; then
        error_log "Target workspace must be specified either as an environment variable [TF_WORKSPACE] or via input argument [workspace]."
        exit 1
    fi

    if [[ -n "$INPUT_PROJECT" ]]; then
        export TF_PROJECT=$INPUT_PROJECT;
    elif [[ ! -v TF_PROJECT ]]; then
        export TF_PROJECT="Default Project"
    fi

    if [[ "$INPUT_VARIABLES" != "" ]]; then
        TMP_VAR_FILE="$STEP_TMP_DIR/variables.tfvars"
        echo "$INPUT_VARIABLES" > $TMP_VAR_FILE
    fi

    if [[ "$INPUT_ENVIRONMENT_VARIABLES" != "" ]]; then
        TMP_ENVIRONMENT_VAR_FILE="$STEP_TMP_DIR/environment_variables.tfvars"
        echo "$INPUT_ENVIRONMENT_VARIABLES" > $TMP_ENVIRONMENT_VAR_FILE
    fi

    if [[ "$INPUT_EXECUTION_MODE" == "" ]]; then
        INPUT_EXECUTION_MODE="remote"
    fi

    if [[ "$INPUT_WORKING_DIRECTORY" == "" ]]; then
        INPUT_WORKING_DIRECTORY="."
    fi

    if [[ "$INPUT_TERRAFORM_VERSION" == "" ]]; then
        INPUT_TERRAFORM_VERSION="latest"
    fi

    if [[ "$INPUT_MESSAGE" == "" ]]; then
        INPUT_MESSAGE="Created by GitHub Actions CI"
    fi

    if [[ "$INPUT_LABEL" == "" ]]; then
        INPUT_LABEL="Workspace \`\`\`$TF_WORKSPACE\`\`\`"
    fi
}

##
# Update a *.tar.gz file to be used in a new run via tfci CLI tool (written in Golang).
#
function upload-configuration-version {
    local tfci_output_path
    local tfci_error_path

    tfci_output_path="$INPUT_PATH/tfci-upload-cv-output.stdout"
    tfci_error_path="$INPUT_PATH/tfci-upload-cv-error.stderr"
    
    if [ "$IS_SPECULATIVE" = true ] ; then
        tfci \
            --hostname "$TF_CLOUD_HOSTNAME" \
            --organization "$TF_CLOUD_ORGANIZATION" \
            upload \
            --workspace "$TF_WORKSPACE" \
            --speculative true \
        2>"$tfci_error_path" \
        | tee "$tfci_output_path"
    else
        tfci \
            --hostname "$TF_CLOUD_HOSTNAME" \
            --organization "$TF_CLOUD_ORGANIZATION" \
            upload \
            --workspace "$TF_WORKSPACE" \
        2>"$tfci_error_path" \
        | tee "$tfci_output_path"
    fi

    result=$(tfci_output "$tfci_output_path")
    printf "\n\n" >> "$GITHUB_OUTPUT"

    TF_CICD_CONFIGURATION_VERSION=$result
}

##
# Discard an existing run via tfci CLI tool (written in Golang).
#
function discard-run {
    local tfci_output_path
    local tfci_error_path

    tfci_output_path="$INPUT_PATH/tfci-discard-run-output.stdout"
    tfci_error_path="$INPUT_PATH/tfci-discard-run-error.stderr"

    tfci \
        --hostname "$TF_CLOUD_HOSTNAME" \
        --organization "$TF_CLOUD_ORGANIZATION" \
        run \
        discard \
        --run "$(echo "$TF_CICD_PLAN" | jq -r '.run_id')" \
        --comment "Discarded by GitHub Actions CI" \
    2>"$tfci_error_path" \
    | tee "$tfci_output_path"

    result=$(tfci_output "$tfci_output_path")
    printf "\n\n" >> "$GITHUB_OUTPUT"
}

##
# Create a new run with configuration-version (either speculative or to be applied via [execute-apply] function) via tfci CLI tool (written in Golang).
#
function execute-plan {
    local tfci_output_path
    local tfci_error_path

    tfci_output_path="$INPUT_PATH/tfci-plan-output.stdout"
    tfci_error_path="$INPUT_PATH/tfci-plan-error.stderr"

    set +e

    if [ "$IS_SPECULATIVE" = true ] ; then
        tfci \
            --hostname "$TF_CLOUD_HOSTNAME" \
            --organization "$TF_CLOUD_ORGANIZATION" \
            run \
            create \
            --workspace "$TF_WORKSPACE" \
            --configuration_version "$(echo "$TF_CICD_CONFIGURATION_VERSION" | jq -r '.configuration_version_id')" \
            --message "$INPUT_MESSAGE" \
            --plan-only "$IS_SPECULATIVE" \
        2>"$tfci_error_path" \
        | tee "$tfci_output_path"
    else
        tfci \
            --hostname "$TF_CLOUD_HOSTNAME" \
            --organization "$TF_CLOUD_ORGANIZATION" \
            run \
            create \
            --workspace "$TF_WORKSPACE" \
            --configuration_version "$(echo "$TF_CICD_CONFIGURATION_VERSION" | jq -r '.configuration_version_id')" \
            --message "$INPUT_MESSAGE" \
        2>"$tfci_error_path" \
        | tee "$tfci_output_path"
    fi

    PLAN_EXIT="$?"

    if [[ $PLAN_EXIT != 0 ]]; then
        error_log "$(cat "$tfci_error_path")"
    fi

    result=$(tfci_output "$tfci_output_path")
    printf "\n\n" >> "$GITHUB_OUTPUT"
    
    export TF_CICD_PLAN=$result

    set -e
}

##
# Apply an existing run via tfci CLI tool (written in Golang).
#
function execute-apply {
    local tfci_output_path
    local tfci_error_path

    tfci_output_path="$INPUT_PATH/tfci-apply-output.stdout"
    tfci_error_path="$INPUT_PATH/tfci-apply-error.stderr"

    set +e

    tfci \
        --hostname "$TF_CLOUD_HOSTNAME" \
        --organization "$TF_CLOUD_ORGANIZATION" \
        run \
        apply \
        --run "$(echo "$TF_CICD_PLAN" | jq -r '.run_id')" \
        --comment "Applied by GitHub Actions CI" \
    2>"$tfci_error_path" \
    | tee "$tfci_output_path"

    APPLY_EXIT="$?"
    
    if [[ $APPLY_EXIT != 0 ]]; then
        error_log "$(cat "$tfci_error_path")"
    fi

    result=$(tfci_output "$tfci_output_path")
    printf "\n\n" >> "$GITHUB_OUTPUT"
    
    export TF_CICD_APPLY=$result

    set -e
}

##
# Provide file with markdown summary for plan execution.
#
function write-plan-summary() {
    local label
    local status
    local run_link
    local imports
    local additions
    local changes
    local destructions
    local plan_summary_file_path
    local execution_log_file_path
    local run_tasks_summary_file_path
    local policy_check_summary_file_path

    label="$1"
    status="$(echo "$2" | jq -r '.status')"
    run_link="$(echo "$2" | jq -r '.run_link')"
    imports="$(echo "$2" | jq -r '.to_import')"
    additions="$(echo "$2" | jq -r '.to_add')"
    changes="$(echo "$2" | jq -r '.to_change')"
    destructions="$(echo "$2" | jq -r '.to_destroy')"
    plan_summary_file_path="$(echo "$2" | jq -r '.plan_summary_file_path')"
    execution_log_file_path="$(echo "$2" | jq -r '.execution_log_file_path')"
    run_tasks_summary_file_path="$(echo "$2" | jq -r '.run_tasks_summary_file_path')"
    policy_check_summary_file_path="$(echo "$2" | jq -r '.policy_check_summary_file_path')"

    echo "To Import $imports, To Add $additions, To Change $changes, To Destroy $destructions"

    PLAN_SUMMARY="$INPUT_PATH/plan-summary-comment.txt"

    if [[ $status == *"applied"* || $status == *"finished"* || $status == *"planned"* || $status == *"policy_checked"* || $status == *"post_plan_completed"* ]]; then
        status_symbol=":green_circle:"
    elif [[ $status == *"error"* || $status == *"fail"* ]]; then
        status_symbol=":red_circle:"
    elif [[ $status == *"override"* ]]; then
        status_symbol=":orange_circle:"
    else
        status_symbol=":black_circle:"
    fi

    github_workflow_run_link="$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/actions/runs/$GITHUB_RUN_ID"

    summary_base=$(cat <<'EOM'
#### Terraform Plan Results for %s
#### Run Status: ```%s``` %s
#### Link: %s
#### Workflow Run: %s
#### Plan: %s to Import, %s to Add, %s to Change, %s to Destroy.
EOM
)
    # shellcheck disable=SC2059
    printf "$summary_base" "$label" "$status" "$status_symbol" "$run_link" "$github_workflow_run_link" "$imports" "$additions" "$changes" "$destructions" >> "$PLAN_SUMMARY"

    if [[ -s $plan_summary_file_path ]]; then        
        {
            printf "\n<details>\n<summary>Full Overview of Changes:</summary>\n\n\`\`\`hcl\n"
            cat "$plan_summary_file_path"
            printf "\n\`\`\`\n</details>\n\n" 
        } >> "$PLAN_SUMMARY"
    fi

    if [[ -s $execution_log_file_path ]]; then        
        {
            printf "\n<details>\n<summary>Execution Log (last 100 lines):</summary>\n\n\`\`\`shell\n"
            tail -n 100 "$execution_log_file_path"
            printf "\n\`\`\`\n</details>\n\n"
        } >> "$PLAN_SUMMARY"
    fi

    if [[ -s $run_tasks_summary_file_path ]]; then        
        {
            printf "\n<details>\n<summary>Run Task Results:</summary>\n\n\`\`\`text\n"
            cat "$run_tasks_summary_file_path"
            printf "\n\`\`\`\n</details>\n\n"
        } >> "$PLAN_SUMMARY"
    fi

    if [[ -s $policy_check_summary_file_path ]]; then        
        {
            printf "\n<details>\n<summary>Policy Check Results:</summary>\n\n\`\`\`text\n"
            cat "$policy_check_summary_file_path"
            printf "\n\`\`\`\n</details>\n\n"
        } >> "$PLAN_SUMMARY"
    fi

    printf "Actor: %s |  Event: \`%s\` |  Workflow: \`%s\`\n" "@$GITHUB_ACTOR" "$GITHUB_EVENT_NAME" "$GITHUB_WORKFLOW" >> "$PLAN_SUMMARY"

    export PLAN_SUMMARY
}

##
# Provide file with markdown summary for apply execution.
#
function write-apply-summary() {
    local status
    local imports
    local additions
    local changes
    local destructions
    local execution_log_file_path

    status="$(echo "$1" | jq -r '.status')"
    imports="$(echo "$1" | jq -r '.to_import')"
    additions="$(echo "$1" | jq -r '.to_add')"
    changes="$(echo "$1" | jq -r '.to_change')"
    destructions="$(echo "$1" | jq -r '.to_destroy')"
    execution_log_file_path="$(echo "$1" | jq -r '.execution_log_file_path')"
    run_tasks_summary_file_path="$(echo "$1" | jq -r '.run_tasks_summary_file_path')"
    policy_check_summary_file_path="$(echo "$1" | jq -r '.policy_check_summary_file_path')"

    if [[ $status == *"applied"* || $status == *"finished"* ]]; then
        status_symbol=":green_circle:"
    elif [[ $status == *"error"* || $status == *"fail"* ]]; then
        status_symbol=":red_circle:"
    else
        status_symbol=":black_circle:"
    fi

    APPLY_SUMMARY="$INPUT_PATH/apply-summary-comment.txt"

    summary_base=$(cat <<'EOM'
___
#### Terraform Apply Results
#### Status: ```%s``` %s
#### Applied: %s Imported, %s Added, %s Changed, %s Destroyed.
EOM
)
    # shellcheck disable=SC2059
    printf "$summary_base" "$status" "$status_symbol" "$imports" "$additions" "$changes" "$destructions" >> "$APPLY_SUMMARY"   

    if [[ -s $execution_log_file_path ]]; then        
        {
            printf "\n<details>\n<summary>Execution Log (last 100 lines):</summary>\n\n\`\`\`shell\n"
            tail -n 100 "$execution_log_file_path"
            printf "\n\`\`\`\n</details>\n\n"
        } >> "$APPLY_SUMMARY"
    fi

    if [[ -s $run_tasks_summary_file_path ]]; then        
        {
            printf "\n<details>\n<summary>Run Task Results:</summary>\n\n\`\`\`text\n"
            cat "$run_tasks_summary_file_path"
            printf "\n\`\`\`\n</details>\n\n"
        } >> "$APPLY_SUMMARY"
    fi

    if [[ -s $policy_check_summary_file_path ]]; then        
        {
            printf "\n<details>\n<summary>Policy Check Results:</summary>\n\n\`\`\`text\n"
            cat "$policy_check_summary_file_path"
            printf "\n\`\`\`\n</details>\n\n"
        } >> "$APPLY_SUMMARY"
    fi

    export APPLY_SUMMARY
}
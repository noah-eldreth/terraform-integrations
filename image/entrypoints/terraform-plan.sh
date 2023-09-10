#!/bin/bash

# shellcheck disable=SC1091
source /usr/local/commands.sh

# shellcheck disable=SC1091
source /usr/local/actions.sh

INPUT_PATH="$STEP_TMP_DIR/terraform-plan"
CICD_SUMMARY="$INPUT_PATH/terraform-cicd-summary.txt"
IS_SPECULATIVE=true
export INPUT_PATH
export IS_SPECULATIVE

mkdir -p "$INPUT_PATH"

set-init-args

# Step 1: Configure the indented workspace; or update as needed if it already exists.
start_group "Configuring target workspace."
result=$(terraform-configure-workspace \
    --hostname "$TF_CLOUD_HOSTNAME" \
    --organization "$TF_CLOUD_ORGANIZATION" \
    --project "$TF_PROJECT" \
    --workspace "$TF_WORKSPACE" \
    --source-url "$GITHUB_SERVER_URL/$GITHUB_REPOSITORY/" \
    --source-name "GitHub Enterprise" \
    --execution-mode "$INPUT_EXECUTION_MODE" \
    --working-directory "$INPUT_WORKING_DIRECTORY" \
    --terraform-version "$INPUT_TERRAFORM_VERSION")
end_group

start_group "Uploading Terraform variables."
# Step 2: Upload environment variables to promote necessary authentication, enable debugging [TF_LOG=DEBUG] or dynamic [TF_VAR_*] variables. 
if [[ ! -v TMP_ENVIRONMENT_VAR_FILE ]]; then
    debug_log "Detected no input for [environment_variables]"
else
    terraform-upload-variable --workspace "$TF_WORKSPACE" --var-file "$TMP_ENVIRONMENT_VAR_FILE" --type "env"
fi
# Step 3: Upload terraform variables provided as direct input from variables.
if [[ ! -v TMP_VAR_FILE ]]; then
    debug_log "Detected no input for [variables]"
else
    terraform-upload-variable --workspace "$TF_WORKSPACE" --var-file "$TMP_VAR_FILE"
fi
# Step 4: Upload terraform variables from input var-file.
if [[ ! -v INPUT_VAR_FILE ]]; then
    debug_log "Detected no input for [var_file]"
else
    for file in $(echo "$INPUT_VAR_FILE" | tr ',' '\n'); do
            if [[ ! -f "$file" ]]; then
                error_log "Path does not exist: \"$file\""
                exit 1
            fi
            terraform-upload-variable --workspace "$TF_WORKSPACE" --var-file "$file"
        done
fi
end_group

# Step 5: Upload configuration version to workspace for run.
start_group "Uploading configuration to workspace."
upload-configuration-version
end_group

# Step 6: Execute Terraform plan. This step will default to failure if the run itself fails.
start_group "Starting plan."
execute-plan
if [[ $(echo "$TF_CICD_PLAN" | jq -r '.run_status') != "planned_and_finished" ]]; then
    PLAN_EXIT=1
fi
end_group

# Step 7: Fetch parsed output for the Terraform plan: execution log, Terraform CLI esc change output, and policy evaluations.
echo "Fetching Results for Terraform Plan..."
result=$(terraform-execution-summary --run-id "$(echo "$TF_CICD_PLAN" | jq -r '.run_id')" --execution-target "plan" --path "$INPUT_PATH")
echo "Fetch Complete."

write-plan-summary "$INPUT_LABEL" "$result"
cat "$PLAN_SUMMARY" >> "$CICD_SUMMARY"
# Step 8: Update GitHub Pull Request (if applicable) with results from plan execution. 
if [[ "$GITHUB_EVENT_NAME" == "pull_request" \
    || "$GITHUB_EVENT_NAME" == "issue_comment" \
    || "$GITHUB_EVENT_NAME" == "pull_request_review_comment" \
    || "$GITHUB_EVENT_NAME" == "pull_request_target" \
    || "$GITHUB_EVENT_NAME" == "pull_request_review" \
    || "$GITHUB_EVENT_NAME" == "repository_dispatch" ]]; then
    github-pull-request-comment --comment "$PLAN_SUMMARY" --label "$INPUT_LABEL"
fi

cat "$CICD_SUMMARY" >> "$GITHUB_STEP_SUMMARY"

if [[ $PLAN_EXIT -eq 0 ]]; then
    echo "Terraform run execution complete."
    exit
else 
    error_log "Terraform run failed. Please review run: $(echo "$TF_CICD_PLAN" | jq -r '.run_link')"
    exit "$PLAN_EXIT"
fi

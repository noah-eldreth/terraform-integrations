# Terraform | Docker Action | Execute Plan

## Execution Summary
This action configures the terraform workspace, uploads the deployment configuration, creates a speculative run, and generates a plan summary from run output.
> 1. Configure the indented workspace; or update as needed if it already exists.
> 2. Upload environment variables to promote necessary authentication, enable debugging [TF_LOG=DEBUG] or dynamic [TF_VAR_*] variables.
> 3. Upload terraform variables provided as direct input from variables.
> 4. Upload terraform variables from input var>file.
> 5. Upload configuration version to workspace for run.
> 6. Execute Terraform plan. This will default to failure if the run itself fails.
> 7. Fetch parsed output for the Terraform plan: execution log, Terraform CLI esc change output, and policy evaluations.
> 8. Update GitHub Pull Request (if applicable) with results from plan execution.

## Inputs
* `hostname`
  Terraform Enterprise/Cloud target hostname. Can instead be set via 'TF_CLOUD_HOSTNAME' environment variable.
  - Type: string
  - Optional
  - Default: ```app.terraform.io```


* `organization`
  Target Terraform Organization. Can instead be set via 'TF_CLOUD_ORGANIZATION' environment variable.
  - Type: string
  - Optional


* `workspace`
  Name of target Workspace. Can instead be set via 'TF_WORKSPACE' environment variable.
  - Type: string
  - Optional


* `project`
  Name of target Project which will manage Workspace. Can instead be set via 'TF_PROJECT' environment variable.
  - Type: string
  - Optional
  - Default: ```Default Project```


* `execution_mode`
  Workspace execution-mode; remote or agent. (Remote execution will use HashiCorp managed runner to perform run. Agent will instead use a self-hosted runner.)
  - Type: string
  - Optional
  - Default: ```remote```


* `working_directory`
  Relative directory to applicable *.tf files.
  - Type: string
  - Optional
  - Default: ```"."```


* `terraform_version`
  Terraform CLI version to use during run execution. 
  - Type: string
  - Optional
  - Default: ```latest```


* `var_file`
  Relative path to *.tfvar(.json) files to load run-specific variables.
  - Type: list
  - Optional
  
  Example:
  ```yml
  var_file: |
      variables/common.tfvars.json
      variables/dev.tfvars.json
  ```


* `variables`
  List of variables to push to target workspace. May be written in JSON or HCL.
  - Type: list
  - Optional
  
  Example:
  ```yml
  variables: |
      instance_type="db.t4g.micro"
      engine="postgresql"
      dbo_user="${{ secrets.rds_username }}"
      dbo_pass="${{ secrets.rds_password }}"
  ```

* `environment_variables`
  List of environment variables to push to target workspace. May be written in JSON or HCL.
  - Type: list
  - Optional
  
  Example: 
  ```yml
  environment_variables: | 
      TFC_AWS_RUN_ROLE_ARN="arn:aws:iam::111111111111:role/terraform-cloud-oidc-role"
      TFC_AWS_PROVIDER_AUTH=true
      AWS_REGION="us-east-1"
  ```


* `message`
  Message to write to explain trigger for Terraform run. Will Default to 'Created by GitHub Actions CI'.
  - Type: string
  - Optional


* `label`
  Header/Label for Pull Request Comment. Will also be used to identify existing Comment.
  - Type: string
  - Optional

## Environment Variables
* `GITHUB_TOKEN`
  The GitHub authorization token to use to promote updates to new or existing Pull Request comments. The token provided by GitHub Actions can be used - it can be passed by using the ```${{ secrets.GITHUB_TOKEN }}``` expression, e.g.

  The minimum permissions are ```pull-requests: write```, and also likely need ```contents: read``` so the job can checkout the repo.
  - Type: string
  - Required (if invocating action via Pull Request.)

  Example:
  ```yml
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  ```

* `TF_API_TOKEN`
  The Terraform Enterprise/Cloud authorization token to use in communicating with api to maintain workspaces and manage plan/apply runs. This token should be specific to intended organization. Best practice is to leverage a team token acting as a service account under organization. 

  The recommends level of permissions are admin privileges against all workspaces (org permissions) which is required to create/configure new workspaces automatically, and also admin privileges over projects. 

  Alternatively, for least-privilege.. token can be prescribed administrative permissions as the workspace level.
  - Type: string
  - Required

  Example:
  ```yml
  env:
    TF_API_TOKEN: ${{ secrets.TF_API_TOKEN }}
  ```

* `TF_CLOUD_HOSTNAME`
  The target Terraform Enterprise/Cloud hostname: ```app.terraform.io```
  - Type: string
  - Optional

  Example:
  ```yml
  env:
    TF_CLOUD_HOSTNAME: app.terraform.io
  ```

* `TF_CLOUD_ORGANIZATION`
  The target Terraform Enterprise/Cloud organization
  - Type: string
  - Optional (Required if input ```organization``` is not provided.)

  Example:
  ```yml
  env:
    TF_CLOUD_ORGANIZATION: your-organization
  ```

* `TF_PROJECT`
  The target Terraform Enterprise/Cloud project: ```Default Project```
  - Type: string
  - Optional

  Example:
  ```yml
  env:
    TF_PROJECT: Default Project
  ```

* `TF_WORKSPACE`
  The target Terraform Enterprise/Cloud organization
  - Type: string
  - Optional (Required if input ```workspace``` is not provided.)

  Example:
  ```yml
  env:
    TF_WORKSPACE: "" # Desired workspace name
  ```

## Outputs
* `status`
    The result of the operation. Possible values are `Success`, `Error` or `Timeout`
    - Type: string

* `configuration_version_id`
    The Configuration Version ID that was created.
    - Type: string

* `configuration_version_status`
    Current status of the created configuration version.
    - Type: string

* `run_id`
    The ID of the created run.
    - Type: string

* `run_status`
    The current status of the Terraform Cloud run.
    - Type: string

* `run_message`
    The message attribute of the shown run.
    - Type: string

* `run_link`
    Link to view the run in Terraform Cloud.
    - Type: string

* `plan_id`
    The ID of the plan, associated to the created run.
    - Type: string

* `plan_status`
    The plan status for the associated run.
    - Type: string

* `cost_estimation_id`
    The ID of the cost estimation for the associated run. (If cost estimation is enabled)
    - Type: string

* `cost_estimation_status`
    The cost estimation status for the associated run. (If cost estimation is enabled)
    - Type: string

* `workspace_id`
    The ID of the Terraform workspace, associated to the created run.
    - Type: string

* `project_id`
    The ID of the Terraform project that owns targeted workspace.
    - Type: string

* `changes`
    True if any imports, additions, updates, or destructions are denoted in plan; otherwise False.
    - Type: bool

* `resource_count`
    The number of resources managed by target workspace.
    - Type: int

* `resource_imports`
    Speculated number of resources to be imported by configuration.
    - Type: int

* `resource_additions`
    Speculated number of resources to be created by configuration.
    - Type: int

* `resource_changes`
    Speculated number of resources to be updated by configuration.
    - Type: int

* `resource_destructions`
    Speculated number of resources to be destroyed by configuration.
    - Type: int


## Example Usage
This is an example where-in a plan or speculative run is executed for a new Pull Request.
```yml
name: Terraform Plan

# Criteria for Execution
on: 
  pull_request:
    branches: 
      - develop
      - feature/**
      - release/**
      
# Required Permissions by GITHUB_TOKEN
permissions: 
  id-token: write
  contents: read
  pull-requests: write
  actions: read
  deployments: write

# Sequential Jobs for Execution
jobs:
  tfops:
    name: Terraform Plan
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    env:
      TF_CLOUD_HOSTNAME: app.terraform.io
      TF_CLOUD_ORGANIZATION: your-organization
      TF_API_TOKEN: ${{ secrets.TF_API_TOKEN }}
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
    steps:
      - name: Checkout Configuration
        uses: actions/checkout@v3
        with:
          ref: ${{ github.event.pull_request.head.ref }}
          repository: ${{ github.event.pull_request.head.repo.full_name }}

      - name: Terraform Plan
        id: plan
        uses: noah-eldreth/terraform-integrations/terraform-plan@v1
        with:
          workspace: "" # Enter a valid workspace name
          working_directory: "."
          var_file: |
            variables/common.tfvars.json
            variables/development.tfvars.json
          environment_variables: | 
            TFC_AWS_RUN_ROLE_ARN="arn:aws:iam::111111111111:role/terraform-cloud-oidc-role"
            TFC_AWS_PROVIDER_AUTH=true
            AWS_REGION="us-east-1"
          message: "Triggered by: [Actor: ${{ github.actor }}; Ref: ${{ github.server_url }}/${{ github.repository }}/pull/${{ github.event.number }}]"
```
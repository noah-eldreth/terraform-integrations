# Terraform Enterprise/Cloud | Integrations
This repository aggregates all applicable workflows/actions/scripts/etc. leveraged in cicd pipelines that administrate infrastructure-as-code deployments using (you guessed it) Terraform. 

#### :warning: These Actions/Workflows Operate Under the Assumption You Are Using Terraform Enterprise/Cloud :warning:
If you intend on using OSS Terraform.. this repository's actions and workflows will not function correctly. 
When using a CLI based integration a Terraform backend is declared in code like-so: [available backends](https://developer.hashicorp.com/terraform/language/settings/backends/configuration). 

Here, workflows/actions ignore backend declarations and explicitly target new/existing workspaces hosted via SaaS or Enterprise license. Additionally, if you already are using an OSS backend (such as Amazon S3) and you inject this repositories workflows into your cicd - you should expect duplication exceptions during deployment as Terraform Enterprise/Cloud is not going to have awareness of your pre-existing state file(s). 

## Introduction
By using GitHub Actions we can automate the deployment of infrastructure during standard Git Operations. Written here are actions, and scripts that enable engineers and developers to plan or apply Infrastructure-as-Code without the burden of maintaining cloud or enterprise workspaces manually; this repository helps minimize overhead (which holistically vastly outweighs the heap of manual configuration required to enable similar functionality while simultaniously ensuring consistent execution).

## Available Actions
### [Terraform Plan](./terraform-plan)
The ```noah-eldreth/terraform-integrations/terraform-plan``` action abstracts many traditionally manual tasks: workspace maintainence, promoting appropriate env/terraform variables, CLI version updates, configuring source control, etc. 
Any new or existing workspaces can be engineered exactly to spec prior to performing a speculative run. Additionally, workspaces can be associated to specific projects and assigned to agent pools automatically. 

Speculative runs can be configured with a suitable range of customization options, and all output is reflected back into GitHub via summaries and Pull Request comments. This includes: 
> 1. 📖 Terraform CLI-like changes. The goal being to fully replicate true plan output for greatest ease-of-use. 
> 2. ⚙️ Tailed plan-stage execution logs. This is very useful when trying to identify errors quickly without having to drill down into Terraform Enterprise/Cloud.
> 3. 📰 Workspace Run-Task results.
> 4. 📃 Sentinel Policy-Check results.

### Example Usage
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

### [Terraform Apply](./terraform-apply)
The ```noah-eldreth/terraform-integrations/terraform-apply``` action will perform identical logic to the above ```terraform-plan``` action, however as implied it will deploy speculated changes. In the event of non-terminating failures (such as 
failed sentinel policy checks) runs will be discarded so as to prevent blocking subsequent applies.

### Example Usage
```yml
name: Terraform Apply

# Criteria for Execution
on: 
  pull_request:
    branches: 
      - feature/**
      - release/**
    type:
      - closed
      
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
    name: Terraform Apply
    if: github.event_name == 'pull_request' && github.event.pull_request.merged == true
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

      - name: Terraform Apply
        id: apply
        uses: noah-eldreth/terraform-integrations/terraform-apply@v1
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

## Authors
#### Code Managed/Owned By: [Noah Eldreth](mailto:noaheldreth12@gmail.com)
All workflows/actions etc. are written and maintained by amazing contributors found [here](https://github.com/noah-eldreth/terraform-integrations/graphs/contributors).

## Contributors
If you are interested in adding a feature and/or update to this repository please write a new issue or pull-request. 

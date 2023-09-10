#!/usr/bin/env python
from setuptools import find_packages, setup

setup(
    name="terraform-interations",
    version="1.0.0",
    packages=find_packages("src"),
    package_dir={"": "src"},
    entry_points={
        "console_scripts": [
            "terraform-parse-cicd-config=terraform_parse_cicd_config.__main__:main",
            "terraform-configure-workspace=terraform_configure_workspace.__main__:main",
            "terraform-execution-summary=terraform_execution_summary.__main__:main",
            "terraform-upload-variable=terraform_upload_variable.__main__:main",
            "terraform-state-outputs=terraform_state_outputs.__main__:main",
            "github-pull-request-comment=github_pull_request_comment.__main__:main",
        ]
    },
    install_requires=["requests", "pyyaml", "cfgv", "terrasnek", "python-hcl2"],
)

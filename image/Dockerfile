# We're extrapolating tfci CLI tool which instruments Terraform runs via API
# Tool is written in Golang; we push to image's /user/local/bin to execute as we would typical terraform CLI commands. 
FROM hashicorp/tfci:v1.0.3 AS tfci

# Pull From Python 3 Container
FROM python:3.11.4-slim

# Relevant Environment Variables
ENV CHECKPOINT_DISABLE=true
ENV TF_IN_AUTOMATION=true
ENV TF_INPUT=false
ENV TF_PLUGIN_CACHE_DIR=/usr/local/share/terraform/plugin-cache
ENV PIP_ROOT_USER_ACTION=ignore
ENV TF_VERIFY=true

# Download and install required tools while keeping image as lightweight as possible
RUN apt-get update  \
 && apt-get install --no-install-recommends -y \
    git \
    ssh \
    tar \
    gzip \
    ca-certificates \
    curl \
    unzip \
    jq \
    wget \
    gpg \
    gpg-agent \
    dirmngr \
 && rm -rf /var/lib/apt/lists/*

# Install Python /src/ dependencies
COPY requirements.txt /requirements.txt
RUN pip install -r /requirements.txt

# Install site-package for terraform-integrations
COPY src/ /tmp/src/
COPY setup.py /tmp/
RUN sed -i "s|version='.*'|version=\'${VERSION}\'|" /tmp/setup.py \
 && pip install /tmp \
 && rm -rf /tmp/src /tmp/setup.py

# Install tfci CLI tool onto imaged derived from Python base
COPY --from=tfci /usr/local/bin/tfci /usr/local/bin/tfci

# Migrate Docker action shells scripts that act as "entrypoint" into execution
# Also ensure all entrypoint shell scripts are executable
COPY entrypoints/ /entrypoints/
RUN chmod -R +x /entrypoints/

COPY actions.sh /usr/local/actions.sh
RUN chmod +x /usr/local/actions.sh

# Migrate GitHub Actions commands which assist in UI output
COPY commands.sh /usr/local/commands.sh

# Migrate tools scripts that simplify logic for bash entrypoints
COPY tools/tfci_output.py /usr/local/bin/tfci_output
RUN chmod +x /usr/local/bin/tfci_output

LABEL org.opencontainers.image.title="terraform-integrations"
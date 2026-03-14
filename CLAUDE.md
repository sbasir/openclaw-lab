# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Pulumi IaC (Python) for deploying the OpenClaw AI agent framework on AWS Spot EC2. Two independent Pulumi stacks sharing the same stack name (e.g., both `dev.uae`):

- **`platform/`** — Long-lived shared infra: GitHub OIDC provider, ECR repository, IAM role for GHA, S3 buckets (backups + bootstrap scripts). Deploy first.
- **`ec2-spot/`** — Ephemeral compute: VPC, security group, Spot instance, EBS, EIP, CloudWatch dashboard. Cross-stack references to platform via `pulumi.StackReference`.

Stack naming: `{env}.{region-alias}` (e.g., `dev.uae` → me-central-1, `dev.mumbai` → ap-south-1).

## Commands

```bash
make install          # Install deps for both stacks
make ci               # Full CI: install → lint → mypy → format → test
make lint             # ruff check (both stacks)
make mypy             # mypy strict (both stacks)
make format           # ruff format (both stacks)
make test             # pytest (ec2-spot only)

# Run a single test:
cd ec2-spot && .venv/bin/python -m pytest tests/test_network_helpers.py::TestCanonicalize::test_normalizes_host_bits_to_network_address -v

# Infrastructure (all require STACK=dev.uae or similar)
make ec2-spot-preview STACK=dev.uae
make ec2-spot-up STACK=dev.uae
make platform-preview STACK=dev.uae
make platform-up STACK=dev.uae

# GitHub Actions local testing (requires `act` CLI)
make gh-act-ci
make actions-lint
```

## Architecture

### Pure-Python Helpers (Pulumi-Free, Testable)

`ec2-spot/network_helpers.py`, `template_helpers.py`, `user_data.py`, `dashboard_builder.py` intentionally avoid Pulumi imports so they can be unit tested with pytest. All tests live in `ec2-spot/tests/`.

### Cloud-Init via Jinja2 Templates

Templates in `ec2-spot/templates/` are rendered at deploy time:
- `cloud-config.yaml.j2` — main cloud-init (installs Docker, CloudWatch agent, fetches secrets from SSM, starts OpenClaw)
- `openclaw-service.conf` — systemd unit (templated with ECR registry + region)
- `docker-compose.yaml`, `cloudwatch-agent-config.json` — uploaded to S3 scripts bucket and downloaded at boot (keeps cloud-init under 16KB limit)

Template rendering: `template_helpers.render_template(name, context)` for Jinja2, `load_template_source(filename)` for raw embedding.

### Cross-Stack References

In `ec2-spot/__main__.py`, platform outputs are consumed via:
```python
platform_stack = pulumi.StackReference(f"{pulumi.get_organization()}/openclaw-platform/{pulumi.get_stack()}")
ecr_repository_url = platform_stack.require_output("ecr_repository_url")
```
Both stacks must use the same stack name for this to resolve correctly.

### Secret & Data Lifecycle

- **Secrets**: SSM Parameter Store (`/openclaw-lab/dotenv`) → fetched at service start into `/run/openclaw/.env` (ephemeral tmpfs)
- **Data**: Root EBS at `/opt/openclaw` (includes `.openclaw/` state)
- **Backups**: S3 sync every 20 min via systemd timer; restored from S3 at boot

## Code Conventions

- Python 3.14+, mypy strict mode, ruff for linting/formatting
- Each stack has its own virtualenv (managed by `pulumi install`)
- CIDR helpers use `ipaddress.IPv4Network(..., strict=False)` to match AWS canonicalization behavior
- No SSH — SSM Session Manager only; security groups block all inbound
- `STACK` is required for all infra Make targets
- `.env` is gitignored and must never be committed

# OpenClaw Lab

Infrastructure-as-code for running OpenClaw on AWS using:

- A Spot EC2 instance for workload runtime (`ec2-spot` stack)
- Shared platform resources like ECR and GitHub OIDC role (`platform` stack)
- GitHub Actions workflows for preview, deploy, destroy, and image publishing

## Repository Structure

- `ec2-spot/`: Pulumi program for VPC/networking, security group, IAM instance profile, Spot instance, and EIP
- `platform/`: Pulumi program for GitHub OIDC deploy role and ECR repository
- `.github/workflows/`: CI/CD workflows
- `Makefile`: Local developer and operations commands

## Prerequisites

- AWS account with permissions for EC2, IAM, ECR, and SSM
- Pulumi CLI authenticated to your Pulumi organization
- Python and `uv`/Pulumi-managed virtual environments
- AWS CLI configured locally

## Quickstart

1. Install dependencies:

```bash
make install
```

2. Configure required values:

- In `platform` stack config, set `github_repo` (for example: `sbasir/openclaw-lab`)
- Configure AWS region and credentials in your environment

3. Deploy platform resources first:

```bash
make platform-up
```

4. Deploy spot infrastructure:

```bash
make ec2-spot-up
```

5. Validate outputs:

```bash
make platform-output
make ec2-spot-output
```

## Development Commands

```bash
make ci         # Run all CI checks (lint, mypy, format, test)
```

## Runtime Layout (EC2)

- OpenClaw runtime home is `/opt/openclaw` (compose file and state)
- systemd service name is `openclaw.service`
- Docker/ECR login is performed in service pre-start as `ec2-user`
- OpenClaw state path is `/opt/openclaw/.openclaw` (suitable for a detachable data volume)
- Runtime secrets file is `/run/openclaw/.env` (re-hydrated from SSM at service start)

## Persistent Data Volume (EC2 Spot stack)

Optional Pulumi config values for `ec2-spot` stack:

```bash
pulumi config set data_volume_size_gib 20
pulumi config set data_device_name /dev/sdf
pulumi config set data_volume_snapshot_id snap-0123456789abcdef0
```

- A dedicated encrypted EBS volume is created and attached to the Spot instance.
- Cloud-init formats/mounts the data disk at `/opt/openclaw` on first boot.
- The data volume uses Pulumi `retain_on_delete`, so `pulumi destroy` keeps the disk for later re-attach/restore workflows.

You can inspect all available commands with:

```bash
make help
```

## CI/CD Workflows

- `CI`: lint and tests for `ec2-spot` and `platform`
- `Infra Preview`: Pulumi preview on infrastructure changes
- `Infra Up`: manual deployment of both stacks
- `Infra Destroy`: manual destruction of spot infrastructure
- `Build and Push OpenClaw Docker Image`: builds and publishes image to ECR

Detailed workflow documentation is in `.github/WORKFLOWS.md`.

## Security Notes

- Uses AWS OIDC for GitHub Actions (no long-lived AWS keys in CI)
- Enforces IMDSv2 on EC2 instance metadata
- Root EBS volume is encrypted
- Parameter Store is used for runtime secrets (for example `.env` payload)
# OpenClaw Lab

Infrastructure-as-code for running OpenClaw on AWS using:

- A Spot EC2 instance for workload runtime (`ec2-spot` stack)
- Shared platform resources like ECR and GitHub OIDC role (`platform` stack)
- GitHub Actions workflows for preview, deploy, destroy, and image publishing

## Repository Structure

- `ec2-spot/`: Pulumi program for VPC/networking, security group, IAM instance profile, Spot instance, EBS data volume, and EIP
  - `templates/`: Jinja2 templates for cloud-init, systemd service, Docker Compose, and CloudWatch configuration
  - `tests/`: Unit tests for pure-Python helpers
  - Pure-Python helpers: `network_helpers.py`, `template_helpers.py`, `user_data.py`, `dashboard_builder.py`
  - `ARCHITECTURE.md`: Data/secret persistence architecture and runbook
- `platform/`: Pulumi program for GitHub OIDC deploy role and ECR repository
- `.github/workflows/`: CI/CD workflows for lint, test, preview, deploy, and image publishing
  - `WORKFLOWS.md`: Detailed workflow documentation and setup instructions
- `Makefile`: Local developer and operations commands
- `scripts/`: Helper scripts for operational tasks
- `STRUCTURE.md`: Comprehensive file structure reference

For a detailed explanation of each file and directory, see [STRUCTURE.md](STRUCTURE.md).

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

- OpenClaw runtime home is `/opt/openclaw` (compose file, state, and workspace)
- systemd service name is `openclaw.service`
- Docker/ECR login is performed in service pre-start as `ec2-user`
- OpenClaw state path is `/opt/openclaw/.openclaw` (persisted on dedicated EBS data volume)
- Runtime secrets file is `/run/openclaw/.env` (re-hydrated from SSM Parameter Store at service start)
- CloudWatch agent installed and configured for log collection and metrics
- Auto-approve devices script available at `/opt/openclaw/auto-approve-devices.sh`

## Observability

The EC2 Spot stack creates a CloudWatch dashboard (`openclaw-lab-observability`) from `ec2-spot/dashboard_builder.py`.

Current widgets include:

- EC2 CPU utilization (`AWS/EC2`)
- OpenClaw memory usage (`OpenClawLab/EC2: MEM_USED_PERCENT`)
- EC2 status checks
- EC2 network in/out
- OpenClaw container logs (filtered)
- EBS throughput and operations (`AWS/EBS`)
- Disk usage `%` for `/` and `/opt/openclaw` (`OpenClawLab/EC2: DISK_USED_PERCENT`)
- Disk I/O (`OpenClawLab/EC2`)
- SSM command status (`AWS/SSM`)
- EBS performance indicators

CloudWatch Agent now writes logs into a stable log group `/aws/ec2/openclaw-lab` with instance-specific log streams, which the dashboard queries and filters.

Access the dashboard via the `dashboard_url` stack output:
```bash
make ec2-spot-output
# or directly:
cd ec2-spot && pulumi stack output dashboard_url
```

## Persistent Data Volume (EC2 Spot stack)

Pulumi config values for `ec2-spot` stack (`availability_zone` is required; others optional):

```bash
# size of the root EBS volume in GiB (default 15)
pulumi config set root_volume_size_gib 20
# availability zone for the instance
pulumi config set availability_zone me-central-1a
```

Before choosing `availability_zone`, you can inspect recent spot prices:

```bash
make ec2-spot-prices INSTANCE_TYPES="t4g.small t4g.medium" REGION=me-central-1
```

- A dedicated encrypted EBS volume is created and attached to the Spot instance.
- Encryption uses the account's default AWS-managed EBS KMS key (no customer-managed key configured in this stack).
- Cloud-init mounts the data disk at `/opt/openclaw` in `bootcmd` before deferred file writes.
- Attachment name (`/dev/sdf`) is an EC2 mapping hint; on Nitro instances the OS device often appears as `/dev/nvme*`.
- The data volume is tagged for identification; actual backups happen via S3 sync.
- `pulumi destroy` deletes the data volume; recovery is performed by restoring from the S3 bucket.
- AZ selection is deterministic and required (`availability_zone`).

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
- Root EBS volume and data volumes are encrypted (uses AWS-managed EBS KMS key)
- SSM Parameter Store is used for runtime secrets (SecureString type for `.env` payload)
- Least-privilege IAM roles for EC2 instance (SSM, ECR read-only, CloudWatch, Parameter Store)
- Security groups restrict all inbound traffic (access via SSM Session Manager only)
- IPv6 support with egress-only rules

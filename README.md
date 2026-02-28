# OpenClaw Lab

Infrastructure-as-code for running OpenClaw on AWS using:

- A Spot EC2 instance for workload runtime (`ec2-spot` stack)
- Shared platform resources like ECR and GitHub OIDC role (`platform` stack)
- GitHub Actions workflows for preview, deploy, destroy, and image publishing

## Repository Structure

- `ec2-spot/`: Pulumi program for VPC/networking, security group, IAM instance profile, Spot instance, root EBS volume, and EIP
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

- Configure AWS region and credentials in your environment
- Login in to Pulumi and select your organization and project

3. Deploy platform resources first:

- In `platform` stack config, set `github_repo` (for example: `sbasir/openclaw-lab`)
```
cd platform
pulumi config set github_repo your_github_username/your_repo_name
```

Deploy platform resources (OIDC role, ECR repository, S3 buckets etc):
```bash
make platform-up
```

From this step onward, you can run some steps using Github Actions workflows instead of locally if you prefer (see CI/CD workflows below).

4. Build and push the OpenClaw Docker image to ECR:

> A docker engine is required locally to build the image locally, or you can trigger the GitHub Actions workflow `Build and Push OpenClaw Docker Image` which performs the same steps in a GitHub-hosted runner with docker support.

```bash
make gh-act-build-push-openclaw-image
```

5. Store your `.env` secrets in SSM Parameter Store:

```bash
cp ec2-spot/templates/dotenv.example .env

sed -i "s|<ECR_REPOSITORY_URL>|$(make platform-output-json | jq -r '.ecr_repository_url')|g" .env
sed -i "s|<OPENCLAW_GATEWAY_TOKEN>|$(openssl rand -hex 32)|g" .env

make openclaw-dotenv-put-parameter
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

6. Monitor bootstrap logs:

```bash
make ec2-spot-deploy-logs
```

7. Port forwarding for local access to the OpenClaw gateway:

```bash
make openclaw-gateway-port-forward
```

8. Access the OpenClaw gateway at `http://localhost:18789`

## Login to Github Copilot

To enable GitHub Copilot for this repository, you can follow these steps:
```
make openclaw-cli COMMANDS="models auth login-github-copilot"
◇  Authorize ──────────────────────────────╮
│                                          │
│  Visit: https://github.com/login/device  │
│  Code: FC97-1D29                         │
│                                          │
├──────────────────────────────────────────╯
```
Manually navigate to the provided URL, enter the code, and complete the authentication process. This will allow you to use GitHub Copilot's AI-powered code suggestions while working on this repository.

## Set model

In command mode, you can set the model for your session using:

```
make openclaw-cli COMMAND="models set github-copilot/gpt-4o"
```

or in the browser chat interface, you can use the command:

```
/models github-copilot
github-copilot/claude-haiku-4.5
github-copilot/claude-opus-4.5
github-copilot/claude-opus-4.6
github-copilot/claude-sonnet-4
github-copilot/claude-sonnet-4.5
github-copilot/claude-sonnet-4.6
github-copilot/gemini-2.5-pro
github-copilot/gemini-3-flash-preview
github-copilot/gemini-3-pro-preview
github-copilot/gemini-3.1-pro-preview
github-copilot/gpt-4.1
github-copilot/gpt-4o
github-copilot/gpt-5
github-copilot/gpt-5-mini
github-copilot/gpt-5.1
github-copilot/gpt-5.1-codex
github-copilot/gpt-5.1-codex-max
github-copilot/gpt-5.1-codex-mini
github-copilot/gpt-5.2
github-copilot/gpt-5.2-codex
github-copilot/grok-code-fast-1

/model github-copilot/gpt-4o
```
You can also configure in http://localhost:18789/agents once the first model is set.

## Adding Slack Integration

To integrate Slack with OpenClaw, you can follow the documentation for setting up Slack channels and configuring the gateway to send notifications to Slack. This typically involves creating a Slack app, obtaining the necessary credentials (like a webhook URL or bot token), and then updating the OpenClaw gateway configuration to use these credentials for sending messages.

Basically add to the gateway configuration (i.e. `/opt/openclaw/.openclaw/openclaw.json` on the EC2 instance) the relevant Slack integration settings as per the documentation, set it directly in raw mode using the browser interface http://localhost:18789/config


```jsonc
{
  channels: {
    slack: {
      enabled: true,
      mode: "socket",
      appToken: "xapp-...",
      botToken: "xoxb-...",
    },
  },
}
```

For detailed instructions, refer to the official OpenClaw documentation on Slack integration:
https://docs.openclaw.ai/channels/slack#slack
https://docs.openclaw.ai/gateway/configuration-reference#slack

If everything is set up correctly, you should see a pairing notification in your Slack workspace on the first chat to the bot like:
```
OpenClaw: access not configured.

Your Slack user id: U0000AAAA

Pairing code: XXXXXX

Ask the bot owner to approve with:
openclaw pairing approve slack XXXXXX
```

You can run `make openclaw-cli COMMAND="pairing approve slack XXXXXX"` to approve the pairing and complete the integration.

## Development Commands

```bash
make ci         # Run all CI checks (lint, mypy, format, test)
```

## Runtime Layout (EC2)

- OpenClaw runtime home is `/opt/openclaw` (compose file, state, and workspace)
- systemd service name is `openclaw.service`
- Docker/ECR login is performed in service pre-start as `ec2-user`
- OpenClaw state path is `/opt/openclaw/.openclaw` (persisted on the root EBS volume; synced to S3)
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
- Disk usage `%` for `/` and `/opt/openclaw` (`OpenClawLab/EC2: DISK_USED_PERCENT`)
- Disk I/O (`OpenClawLab/EC2`)
- SSM command status (`AWS/SSM`)

CloudWatch Agent now writes logs into a stable log group `/aws/ec2/openclaw-lab` with instance-specific log streams, which the dashboard queries and filters.

Access the dashboard via the `dashboard_url` stack output:
```bash
make ec2-spot-output
# or directly:
cd ec2-spot && pulumi stack output dashboard_url
```

## Root Volume Storage (EC2 Spot stack)

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

- The root EBS volume is encrypted (AWS-managed EBS KMS key by default).
- `/opt/openclaw` lives on the root filesystem and is used for OpenClaw state and workspace data.
- Backups are handled via S3 sync; restoring the bucket data is sufficient for recovery.
- `pulumi destroy` deletes the root volume; data is recovered by restoring from S3.
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
- Root EBS volume is encrypted (uses AWS-managed EBS KMS key)
- SSM Parameter Store is used for runtime secrets (SecureString type for `.env` payload)
- Least-privilege IAM roles for EC2 instance (SSM, ECR read-only, CloudWatch, Parameter Store)
- Security groups restrict all inbound traffic (access via SSM Session Manager only)
- IPv6 support with egress-only rules

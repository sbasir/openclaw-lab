# OpenClaw Lab - AI Agent Coding Instructions

## Project Overview

OpenClaw Lab is a Pulumi-based Infrastructure-as-Code project that manages OpenClaw on AWS using Spot EC2 instances. The project emphasizes **stack separation**, **cloud-init automation**, and **testable pure-Python helpers**.

## Architecture & Stack Structure

**Two independent Pulumi stacks** (same organization, different stack directories):

1. **`platform/`** - Long-lived shared infrastructure:
   - GitHub OIDC provider (account-scoped; skipped if `create_oidc_provider=false`)
   - Private ECR repository for OpenClaw Docker image
   - IAM role for GitHub Actions CI/CD
   - S3 buckets: one for data backups, one for bootstrap scripts
   - Outputs: `ecr_repository_url`, `s3_backup_bucket_name`, `s3_scripts_bucket_name` (all consumed by ec2-spot stack)

2. **`ec2-spot/`** - Ephemeral compute (can be destroyed/recreated):
   - VPC with a single subnet in the configured AZ (IPv4 + IPv6 via calculated CIDR blocks)
   - Security groups (SSM-only access, no SSH), IAM instance profile, Spot instance
   - Root EBS volume sized via stack configuration (encrypted, tagged for DLM)
   - Systemd service for OpenClaw
   - CloudWatch dashboard with 20+ widgets
   - **Cross-stack references** to platform stack for ECR URL, S3 bucket names

**Stack reference pattern** (in `ec2-spot/__main__.py`):
```python
platform_stack = pulumi.StackReference(f"{pulumi.get_organization()}/openclaw-platform/{pulumi.get_stack()}")
ecr_repository_url = platform_stack.require_output("ecr_repository_url")
s3_backup_bucket_name = platform_stack.require_output("s3_backup_bucket_name")
s3_scripts_bucket_name = platform_stack.require_output("s3_scripts_bucket_name")
```

Both stacks must use the **same stack name** (e.g., both `dev.uae`). The cross-stack reference uses `pulumi.get_stack()` to resolve the correct platform stack automatically.

## Multi-Region Deployment

Stack naming convention: `{env}.{region-alias}` (e.g. `dev.uae`, `dev.mumbai`).

| Stack | Region | Config file (both dirs) |
|-------|--------|------------------------|
| `dev.uae` | me-central-1 | `Pulumi.dev.uae.yaml` |
| `dev.mumbai` | ap-south-1 | `Pulumi.dev.mumbai.yaml` |

### GitHub Environments
Each region requires a GitHub Environment (repo Settings → Environments) with:
- `AWS_ROLE_ARN` — the `github_actions_role_arn` output from that region's platform stack
- `AWS_REGION` — the AWS region (e.g. `me-central-1`, `ap-south-1`)

Environment names must match what's in the workflow files: `uae`, `mumbai`.

### Bootstrapping a new region
```bash
# 1. Deploy platform stack first (locally, using existing role ARN or static creds)
cd platform && pulumi stack select dev.mumbai && pulumi up

# 2. Get the new region's role ARN
pulumi stack output github_actions_role_arn

# 3. Create GitHub Environment "mumbai" in repo settings with:
#    AWS_ROLE_ARN = <output from step 2>
#    AWS_REGION   = ap-south-1

# 4. Push images to the new ECR
# (trigger build-push-image workflow, or run locally)

# 5. Deploy ec2-spot stack
cd ../ec2-spot && pulumi stack select dev.mumbai && pulumi up
```

### Renaming the existing `dev` stack to `dev.uae`
The legacy `dev` stack should be renamed when convenient (does not require the region to be online):
```bash
cd platform  && pulumi stack rename dev dev.uae
cd ../ec2-spot && pulumi stack rename dev dev.uae
```
After renaming: update the `uae` GitHub Environment's `AWS_ROLE_ARN` with the value from
`make platform-output` (role ARN may change on next `pulumi up` if not set). Remove
the old `Pulumi.dev.yaml` files from both stack directories once migration is confirmed.

## Key Design Patterns

### 1. Pure-Python Helpers (Testable, Pulumi-Free)

Located in `ec2-spot/network_helpers.py`, `template_helpers.py`, `user_data.py`. These intentionally avoid Pulumi imports to enable unit testing without a running Pulumi runtime.

**Example: Network CIDR calculations**
- `canonicalize_ipv4_cidr()`: Mirrors AWS `CreateVpc` behavior (silently canonicalizes host bits instead of rejecting)
- `allocate_ipv4_subnets(base_cidr, subnet_count, subnet_prefix)`: Returns list of CIDR blocks for each AZ
- Tested in `tests/test_network_helpers.py` with pytest

### 2. Cloud-Init via Jinja2 Templates

OpenClaw bootstrap uses a cloud-init YAML file (`templates/cloud-config.yaml.j2`) rendered at deployment time:

- `template_helpers.load_template_source()`: Read raw template file (for embedding config)
- `template_helpers.render_template(name, context)`: Render Jinja2 template with context dict
- Context includes: ECR registry, AWS region, version pins, service config
- Templates in `ec2-spot/templates/` include:
  - `cloud-config.yaml.j2`: Main cloud-init script (starts Docker, manages secrets)
  - `openclaw-service.conf`: Systemd service unit (templated with registry + region)
  - `docker-compose.yaml`: OpenClaw services definition
  - `cloudwatch-agent-config.json`: CloudWatch agent configuration

### 3. Secret & Data Lifecycle

- **Secrets**: Stored in **AWS SSM Parameter Store** (`/openclaw-lab/dotenv`), fetched at service start into `/run/openclaw/.env` (ephemeral, never on disk)
- **Data**: Persisted on the root EBS volume at `/opt/openclaw` (includes `.openclaw/` state)
- **Backups**: S3 sync every 20 minutes via systemd timer; data is restored from S3 at boot
- **Bootstrap scripts**: `docker-compose.yaml`, `cloudwatch-agent-config.json`, and shell scripts are stored in the S3 scripts bucket and downloaded at boot (to keep cloud-init YAML under the 16KB limit)

### 4. CloudWatch Observability Dashboard

- **Automatic creation**: Dashboard created for each stack deployment
- **Comprehensive metrics**: CPU, memory, disk, network, SSM, and logs
- **Custom namespace**: CloudWatch agent publishes to `OpenClawLab/EC2`
- **Access**: Via `dashboard_url` stack output or AWS Console
- **Widgets**: Modular widget builders in `dashboard_builder.py` (CPU, memory, disk, network, SSM, logs)
- **Log insights**: Integration with CloudWatch Logs for error/warning detection

## Development Workflows

### Installation & Setup
```bash
make install          # Install all deps (runs: install-ec2-spot, install-platform)
```

### Local Testing & Quality
```bash
make lint             # Ruff linting (ec2-spot + platform)
make mypy             # Strict type checking (python 3.14, all files)
make format           # Ruff formatting
make test             # Pytest (ec2-spot tests/)
make ci               # Full check: install → lint → mypy → format → test
```

### Infrastructure Preview & Deploy
```bash
make ec2-spot-preview    # Preview ec2-spot stack changes
make ec2-spot-up         # Deploy ec2-spot (interactive or with AUTO_APPROVE=true)
make ec2-spot-destroy    # Destroy ec2-spot
make ec2-spot-output     # Show stack outputs (instance_id, AMI, etc.)

make platform-preview    # Preview platform stack changes
make platform-up         # Deploy platform
make platform-destroy    # Destroy platform
make platform-output     # Show stack outputs (ECR URL, etc.)
```

### Local GitHub Actions Testing
```bash
make gh-act-ci                          # Run local CI workflow
make gh-act-infra-preview               # Test infra-preview workflow
make gh-act-infra-up                    # Test infra-up workflow (requires AWS credentials)
make gh-act-build-push-openclaw-image   # Test image build/push workflow
```

### Operational Commands
```bash
make openclaw-ec2-connect               # SSH via SSM Session Manager
make openclaw-gateway-session           # Port-forward to OpenClaw Gateway (18789)
make openclaw-cli COMMAND="devices list"   # Run OpenClaw CLI commands
make openclaw-dotenv-put-parameter      # Store .env file in SSM Parameter Store
make ec2-spot-prices INSTANCE_TYPES="t4g.small t4g.medium" REGION=us-east-1
```

## Configuration & Stacks

Configuration is managed via `pulumi config set` (stored in `Pulumi.{stack-name}.yaml`):

**Platform stack** (`platform/`):
- `github_repo` (required): GitHub repo in `owner/repo` format (e.g., `sbasir/openclaw-lab`)
- `create_oidc_provider` (optional): Set to `true` only on the **first region** you deploy. All additional regions must set this to `false` — OIDC provider is account-scoped.

**EC2 Spot stack** (`ec2-spot/`):
- `availability_zone` (required): AZ for instance
- `instance_type` (optional): Default `t4g.small`
- `cidr_block` (optional): VPC CIDR, default `10.0.0.0/16`
- `ami` (optional): Override default Amazon Linux 2023 AMI
- `root_volume_size_gib` (optional): Default `15` (controls size of the root EBS volume)

## Code Conventions & Patterns

### Type Checking & Linting
- **mypy strict mode**: All files checked with `python_version = "3.14"`, `strict = true`
- **ruff**: Linting + formatting (configured in `pyproject.toml`)
- Both stacks have independent virtual environments (via `pulumi install`)

### Testing
- **pytest**: Test files in `tests/` directory
- **Pure-Python helpers are unit-testable**: Network helpers, template rendering functions
- **Pulumi resources not unit-tested**: Use `pulumi preview` to validate resource definitions
- **Run a single test**: `cd ec2-spot && .venv/bin/python -m pytest tests/test_network_helpers.py::TestCanonicalize::test_normalizes_host_bits_to_network_address -v`

### CIDR & Network Calculations
When adding subnet allocation logic:
1. Use `ipaddress.IPv4Network(..., strict=False)` to match AWS CIDR canonicalization
2. Include validation tests that verify host-bit canonicalization
3. Keep logic in pure Python (no Pulumi imports)

### Template Rendering
- Load raw templates via `load_template_source(filename)` for embedding in cloud-init
- Render templated configs via `render_template(filename, context_dict)`
- Jinja2 filters available; common context: `aws_region`, `ecr_registry_domain`, device names

## CI/CD Integration

- **.github/workflows/**: GitHub Actions workflows (lint, test, infra-preview, infra-up, build-push-image)
- **GitHub OIDC**: Provides temporary AWS credentials via `aws-actions/configure-aws-credentials`
- **GitHub Environments** (`uae`, `mumbai`): Store region-specific `AWS_ROLE_ARN` and `AWS_REGION` variables
- **infra-preview**: Runs matrix across all stacks (`dev.uae`, `dev.mumbai`) on push/PR
- **infra-up / infra-destroy**: Accept `stack` as `workflow_dispatch` choice input; deploy/destroy one region at a time
- **build-push-image**: Matrix across all stacks — each job authenticates to its own ECR and pushes independently using per-stack GHA cache scopes
- **Local testing**: Use `make gh-act-*` to test workflows locally (requires `act` CLI); set `STACK=dev.mumbai` to override the default target

## File Structure Reference

```
ec2-spot/
  __main__.py                    # Pulumi stack definition (VPC, EC2, IAM)
  network_helpers.py             # Pure Python CIDR/subnet calculations
  user_data.py                   # Cloud-init script builder
  template_helpers.py            # Jinja2 template loading/rendering
  dashboard_builder.py           # CloudWatch dashboard widget composition
  ARCHITECTURE.md                # Data/secret persistence design notes
  tests/
    test_network_helpers.py      # Unit tests for CIDR logic
    test_template_helpers.py     # Unit tests for template rendering
    test_user_data.py            # Unit tests for user-data builder
    test_s3_lifecycle.py         # Unit tests for S3 snapshot lifecycle
  templates/                     # Jinja2 templates for cloud-init
    cloud-config.yaml.j2         # Main cloud-init script
    openclaw-service.conf        # Systemd service unit template
    docker-compose.yaml          # OpenClaw Docker Compose definition
    cloudwatch-agent-config.json # CloudWatch agent config
    auto-approve-devices.sh      # Device auto-approval helper script
    openclaw-s3-backup.sh        # S3 backup script (runs on 20-min timer)
    openclaw-s3-restore.sh       # S3 restore script (runs at boot)
    dotenv.example               # Example .env configuration

platform/
  __main__.py                    # Pulumi stack definition (OIDC, ECR, IAM role)

.github/
  workflows/                     # GitHub Actions workflows
  copilot-instructions.md        # This file
  WORKFLOWS.md                   # Detailed workflow documentation

Makefile                         # Developer and operations commands
README.md                        # Project overview and quickstart
STRUCTURE.md                     # Comprehensive file structure reference
```

For a complete file-by-file reference, see [STRUCTURE.md](../STRUCTURE.md).

## Common Tasks for AI Agents

1. **Adding a new configuration option**: Add to `ec2-spot/__main__.py` config parsing, document in platform stack if cross-stack, add tests if logic is pure Python, update README quickstart if user-facing
2. **Modifying cloud-init behavior**: Update templates in `ec2-spot/templates/`, test via `make ec2-spot-preview`, validate cloud-init logs via `make ec2-spot-deploy-logs`
3. **Fixing CIDR/subnet logic**: Modify `network_helpers.py`, add test cases to `test_network_helpers.py`, run `make test`
4. **Adding CI/CD capability**: Update `.github/workflows/` YAML files, test locally with `make gh-act-*`, validate with `make actions-lint`
5. **Updating IAM permissions**: Modify role policy JSON in `platform/__main__.py` or `ec2-spot/__main__.py`, preview with `make platform-preview` / `make ec2-spot-preview`

## References
- [Pulumi AWS Provider](https://www.pulumi.com/registry/packages/aws/)
- [Cloud-init Documentation](https://cloud-init.readthedocs.io/)
- [AWS SSM Parameter Store](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store.html)
- [AWS OIDC Provider for GitHub Actions](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
- [STRUCTURE.md](../STRUCTURE.md): Comprehensive file structure reference
- [WORKFLOWS.md](WORKFLOWS.md): GitHub Actions workflow documentation
- [ec2-spot/ARCHITECTURE.md](../ec2-spot/ARCHITECTURE.md): Architecture notes and operational runbook
- [ec2-spot/DASHBOARD.md](../ec2-spot/DASHBOARD.md): CloudWatch Dashboard observability guide

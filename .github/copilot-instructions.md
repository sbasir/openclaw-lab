# OpenClaw Lab - AI Agent Coding Instructions

## Project Overview

OpenClaw Lab is a Pulumi-based Infrastructure-as-Code project that manages OpenClaw on AWS using Spot EC2 instances. The project emphasizes **stack separation**, **cloud-init automation**, and **testable pure-Python helpers**.

## Architecture & Stack Structure

**Two independent Pulumi stacks** (same organization, different stack directories):

1. **`platform/`** - Long-lived shared infrastructure:
   - GitHub OIDC provider (account-scoped; skipped if `create_oidc_provider=false`)
   - ECR repository for OpenClaw Docker image
   - IAM role for GitHub Actions CI/CD
   - Outputs: `ecr_repository_url` (consumed by ec2-spot stack)

2. **`ec2-spot/`** - Ephemeral compute (can be destroyed/recreated):
   - VPC with multi-AZ subnets (IPv4 + IPv6 via calculated CIDR blocks)
   - Security groups, IAM instance profile, Spot instance
   - EBS data volume with DLM-managed snapshots
   - Systemd service for OpenClaw
   - **Cross-stack reference** to platform stack for ECR URL

**Stack reference pattern** (in `ec2-spot/__main__.py`):
```python
platform_stack = pulumi.StackReference(f"{pulumi.get_organization()}/openclaw-platform/{pulumi.get_stack()}")
ecr_repository_url = platform_stack.require_output("ecr_repository_url")
```

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
- Context includes: ECR registry, AWS region, data device name, version pins, service config
- Templates in `ec2-spot/templates/` include:
  - `cloud-config.yaml.j2`: Main cloud-init script (mounts volume, starts Docker, manages secrets)
  - `openclaw-service.conf`: Systemd service unit (templated with registry + region)
  - `docker-compose.yaml`: OpenClaw services definition
  - `cloudwatch-agent-config.json`: CloudWatch agent configuration

### 3. Secret & Data Lifecycle

- **Secrets**: Stored in **AWS SSM Parameter Store**, fetched at service start into `/run/openclaw/.env`
- **Data**: Persisted on dedicated EBS volume at `/opt/openclaw` (includes `.openclaw/` state)
- **Snapshots**: DLM-managed with configurable schedule (default: 24h) and retention (default: 30 days)
- **Recovery**: Set `data_volume_snapshot_id` in stack config, re-deploy to restore

### 4. CloudWatch Observability Dashboard

- **Automatic creation**: Dashboard created for each stack deployment
- **Comprehensive metrics**: CPU, memory, disk, network, EBS, SSM, and logs
- **Custom namespace**: CloudWatch agent publishes to `OpenClawLab/EC2`
- **Access**: Via `dashboard_url` stack output or AWS Console
- **Widgets**: Modular widget builders in `dashboard_builder.py` (CPU, memory, disk, network, EBS, SSM, logs)
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

Configuration is managed via `pulumi config set` (stored in `Pulumi.dev.yaml` or `Pulumi.prod.yaml`):

**Platform stack** (`platform/`):
- `github_repo` (required): GitHub repo in `owner/repo` format (e.g., `sbasir/openclaw-lab`)
- `create_oidc_provider` (optional): Set to `true` only on first setup (OIDC provider is account-scoped)

**EC2 Spot stack** (`ec2-spot/`):
- `availability_zone` (required): AZ for instance + data volume
- `instance_type` (optional): Default `t4g.small`
- `cidr_block` (optional): VPC CIDR, default `10.0.0.0/16`
- `ami` (optional): Override default Amazon Linux 2023 AMI
- `data_volume_size_gib` (optional): Default `20`
- `data_device_name` (optional): Default `/dev/sdf`
- `data_volume_snapshot_id` (optional): Restore from snapshot
- `snapshot_schedule_interval_hours` (optional): Default `24`
- `snapshot_schedule_time` (optional): Required if interval is 24h, format `HH:MM`
- `snapshot_retention_days` (optional): Default `30`, must be `>= 1`

## Code Conventions & Patterns

### Type Checking & Linting
- **mypy strict mode**: All files checked with `python_version = "3.14"`, `strict = true`
- **ruff**: Linting + formatting (configured in `pyproject.toml`)
- Both stacks have independent virtual environments (via `pulumi install`)

### Testing
- **pytest**: Test files in `tests/` directory (e.g., `test_network_helpers.py`)
- **Pure-Python helpers are unit-testable**: Network helpers, template rendering functions
- **Pulumi resources not unit-tested**: Use `pulumi preview` to validate resource definitions

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
- **Role assumption**: `github_actions_role` in platform stack allows repo to assume AWS role
- **Stack references**: Workflows can fetch ECR URL from platform stack to push Docker images
- **Local testing**: Use `make gh-act-*` to test workflows locally (requires `act` CLI)

## File Structure Reference

```
ec2-spot/
  __main__.py                    # Pulumi stack definition (VPC, EC2, EBS, IAM)
  network_helpers.py             # Pure Python CIDR/subnet calculations
  user_data.py                   # Cloud-init script builder
  template_helpers.py            # Jinja2 template loading/rendering
  ARCHITECTURE.md                # Data/secret persistence design notes
  tests/
    test_network_helpers.py      # Unit tests for CIDR logic
    test_template_helpers.py     # Unit tests for template rendering
    test_user_data.py            # Unit tests for user-data builder
  templates/                     # Jinja2 templates for cloud-init
    cloud-config.yaml.j2         # Main cloud-init script
    openclaw-service.conf        # Systemd service unit template
    docker-compose.yaml          # OpenClaw Docker Compose definition
    cloudwatch-agent-config.json # CloudWatch agent config
    auto-approve-devices.sh      # Device auto-approval helper script
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

# OpenClaw Lab - File Structure Reference

This document provides a comprehensive reference of the project's file organization and the purpose of each component.

## Root Directory

```
openclaw-lab/
├── .github/                      # GitHub-specific configuration
├── ec2-spot/                     # EC2 Spot instance Pulumi stack
├── platform/                     # Platform resources Pulumi stack
├── scripts/                      # Helper scripts for operations
├── tmp/                          # Temporary/scratch files (gitignored)
├── .gitignore                    # Git ignore patterns
├── Makefile                      # Developer and operations commands
├── README.md                     # Project overview and quickstart
└── STRUCTURE.md                  # This file
```

## .github/ - GitHub Configuration

```
.github/
├── workflows/                    # GitHub Actions workflow definitions
│   ├── build-push-image.yaml    # Build and push OpenClaw Docker image to ECR
│   ├── ci.yaml                   # Continuous integration (lint, test)
│   ├── infra-destroy.yaml        # Manual infrastructure destruction
│   ├── infra-preview.yaml        # Preview infrastructure changes
│   └── infra-up.yaml             # Deploy infrastructure
├── actionlint.yaml               # Configuration for actionlint tool
├── copilot-instructions.md       # AI coding assistant instructions
└── WORKFLOWS.md                  # Detailed workflow documentation
```

### Workflow Files

- **ci.yaml**: Runs on every push and PR; executes linting and tests for both stacks
- **infra-preview.yaml**: Automatically runs Pulumi preview on infrastructure changes
- **infra-up.yaml**: Manual workflow to deploy both platform and ec2-spot stacks
- **infra-destroy.yaml**: Manual workflow to destroy ec2-spot infrastructure (platform preserved)
- **build-push-image.yaml**: Builds OpenClaw Docker image and pushes to ECR

## ec2-spot/ - EC2 Spot Instance Stack

```
ec2-spot/
├── templates/                    # Jinja2 templates for cloud-init
│   ├── auto-approve-devices.sh   # Helper script for auto-approving device pairings
│   ├── cloud-config.yaml.j2      # Main cloud-init configuration (Jinja2 template)
│   ├── cloudwatch-agent-config.json  # CloudWatch agent configuration
│   ├── docker-compose.yaml       # OpenClaw Docker Compose services definition
│   ├── dotenv.example            # Example .env file for OpenClaw configuration
│   └── openclaw-service.conf     # Systemd service unit for OpenClaw
├── tests/                        # Unit tests for pure-Python helpers
│   ├── test_network_helpers.py   # Tests for CIDR/subnet calculations
│   ├── test_template_helpers.py  # Tests for template loading/rendering
│   └── test_user_data.py         # Tests for user-data script builder
├── __main__.py                   # Pulumi stack definition (entry point)
├── ARCHITECTURE.md               # Architecture notes, data/secret lifecycle, runbook
├── network_helpers.py            # Pure-Python CIDR/subnet calculation utilities
├── Pulumi.dev.yaml               # Pulumi stack configuration for 'dev' environment
├── Pulumi.yaml                   # Pulumi project metadata
├── pyproject.toml                # Python dependencies and tool configuration
├── template_helpers.py           # Jinja2 template loading and rendering utilities
└── user_data.py                  # Cloud-init user-data script builder
```

### Key Files

#### `__main__.py` - Main Stack Definition
Contains the complete infrastructure definition:
- VPC with IPv4 and IPv6 support, multi-AZ subnets
- Internet Gateway and route tables
- Security groups (SSM-only access, no inbound ports)
- EC2 Spot instance with persistent request type
- Elastic IP for stable public addressing
- EBS data volume with encryption
- Data Lifecycle Manager (DLM) policy for automated snapshots
- IAM roles and instance profile (SSM, ECR, CloudWatch, Parameter Store access)
- Cross-stack reference to platform stack for ECR URL
- CloudWatch Dashboard with 20+ observability widgets

#### `network_helpers.py` - Network Utilities
Pure-Python functions for CIDR calculations:
- `canonicalize_ipv4_cidr()`: Mirrors AWS behavior for CIDR canonicalization
- `allocate_ipv4_subnets()`: Calculate subnet CIDRs for multiple AZs
- `allocate_ipv6_subnets()`: Calculate IPv6 subnet CIDRs
- `ipv4_subnets_cidrs()`: High-level IPv4 subnet allocation
- `ipv6_subnets_cidrs()`: High-level IPv6 subnet allocation with Pulumi Output handling

**Design principle**: No Pulumi imports, enabling unit testing without Pulumi runtime.

#### `template_helpers.py` - Template Utilities
Jinja2 template management:
- `render_template()`: Render a Jinja2 template with context dict
- `load_template_source()`: Load raw template file contents (for embedding in cloud-init)

#### `user_data.py` - Cloud-Init Builder
Builds the complete cloud-init YAML:
- `build_user_data()`: Main entry point, renders cloud-config.yaml.j2 with full context
- `extract_ecr_registry_domain()`: Parse ECR registry domain from repository URL

#### `ARCHITECTURE.md` - Design Documentation
Detailed architecture notes:
- Data vs. secret persistence strategy
- Snapshot-first recovery model
- DLM snapshot lifecycle policies
- Operational runbook for common tasks (deploy, restore, snapshot management)
- Troubleshooting guide

#### `DASHBOARD.md` - CloudWatch Dashboard Guide
Comprehensive observability documentation:
- 8-section dashboard layout with 20+ widgets
- Detailed metric explanations and thresholds
- Widget categories (CPU, Memory, Disk, Network, EBS, SSM)
- CloudWatch Logs Insights query guide
- Recommended alarms and cost optimization tips

### Templates Directory

#### `cloud-config.yaml.j2` - Main Cloud-Init Script
Multi-stage cloud-init configuration:
1. Install Docker Compose, CloudWatch agent, jq
2. Format and mount EBS data volume at `/opt/openclaw`
3. Configure and start CloudWatch agent
4. Write systemd service file for OpenClaw
5. Fetch secrets from SSM Parameter Store into `/run/openclaw/.env`
6. Pull Docker images from ECR and start OpenClaw via Docker Compose

#### `openclaw-service.conf` - Systemd Service
Systemd service unit for OpenClaw:
- Pre-start: ECR login using instance profile credentials
- Main: `docker compose up` for OpenClaw services
- Post-stop: `docker compose down` cleanup

#### `docker-compose.yaml` - OpenClaw Services
Docker Compose definition for OpenClaw containers:
- OpenClaw gateway service (API, web UI)
- OpenClaw CLI utility container
- Environment configuration via `.env` file
- Volume mounts for persistent state and workspace

#### `cloudwatch-agent-config.json` - CloudWatch Config
CloudWatch agent configuration:
- Log collection from `/var/log/cloud-init-output.log`
- System metrics (CPU, memory, disk)
- Custom namespace for OpenClaw metrics

#### `auto-approve-devices.sh` - Device Auto-Approval Helper
Bash script to automatically approve pending OpenClaw device pairing requests:
- Safe for dev environments with SSM-only access
- Uses OpenClaw CLI to list and approve pending devices
- Idempotent (safe to run multiple times)

## platform/ - Platform Resources Stack

```
platform/
├── __main__.py                   # Pulumi stack definition (entry point)
├── Pulumi.dev.yaml               # Pulumi stack configuration for 'dev' environment
├── Pulumi.yaml                   # Pulumi project metadata
└── pyproject.toml                # Python dependencies and tool configuration
```

### `__main__.py` - Platform Stack Definition
Long-lived platform resources:
- GitHub OIDC provider (optional, account-scoped)
- IAM role for GitHub Actions with OIDC trust policy
- IAM policies for EC2, EBS, ECR, SSM, DLM, and STS operations
- Private ECR repository for OpenClaw Docker images

**Exports**: `ecr_repository_url`, `oidc_provider_arn`, `github_actions_role_arn`

**Important**: This stack should be deployed BEFORE ec2-spot, as it provides the ECR URL.

## scripts/ - Operational Scripts

```
scripts/
└── ec2-spot-prices.sh            # Query recent EC2 Spot prices by instance type and region
```

### `ec2-spot-prices.sh`
Queries AWS for recent Spot pricing to help choose cost-effective instance types and availability zones.

**Usage**: `make ec2-spot-prices INSTANCE_TYPES="t4g.small t4g.medium" REGION=us-east-1`

## Root-Level Files

### `Makefile` - Command Hub
Comprehensive command set organized by category:

#### Setup Commands
- `make install`: Install dependencies for both stacks
- `make lint`: Run ruff linting on all code
- `make mypy`: Run strict type checking
- `make format`: Auto-format code with ruff
- `make test`: Run pytest unit tests
- `make ci`: Full CI check (install, lint, mypy, format, test)

#### Infrastructure Commands
- `make ec2-spot-preview`: Pulumi preview for EC2 stack
- `make ec2-spot-up`: Deploy EC2 stack
- `make ec2-spot-destroy`: Destroy EC2 stack
- `make ec2-spot-output`: Show EC2 stack outputs
- `make ec2-spot-deploy-logs`: Monitor cloud-init bootstrap logs
- `make platform-preview`: Pulumi preview for platform stack
- `make platform-up`: Deploy platform stack
- `make platform-destroy`: Destroy platform stack
- `make platform-output`: Show platform stack outputs

#### GitHub Actions Commands
- `make actions-lint`: Lint workflow YAML files with actionlint
- `make gh-act-ci`: Run CI workflow locally with act
- `make gh-act-infra-preview`: Run infra-preview locally
- `make gh-act-infra-up`: Run infra-up locally
- `make gh-act-build-push-openclaw-image`: Run image build locally

#### Helpful Commands
- `make openclaw-ec2-connect`: SSH to instance via SSM Session Manager
- `make openclaw-gateway-session`: Port-forward to OpenClaw Gateway (18789)
- `make openclaw-cli COMMAND="..."`: Run OpenClaw CLI commands
- `make openclaw-dotenv-put-parameter`: Store .env in SSM Parameter Store
- `make openclaw-devices-list`: List pending device pairing requests
- `make openclaw-devices-approve-all`: Auto-approve all pending devices
- `make ec2-spot-prices`: Show recent Spot prices
- `make aws-describe-images`: List available Amazon Linux 2023 AMIs

### `README.md` - Project Overview
High-level project introduction:
- Architecture overview
- Quickstart guide
- Configuration options
- Runtime layout
- Security notes

## Configuration Files

### `Pulumi.yaml` (both stacks)
Pulumi project metadata:
- Project name
- Runtime (Python)
- Entry point specification

### `Pulumi.dev.yaml` (both stacks)
Stack-specific configuration values:
- **Platform**: `github_repo`, `create_oidc_provider`
- **EC2 Spot**: `availability_zone`, `instance_type`, `cidr_block`, `ami`, data volume settings, snapshot settings

### `pyproject.toml` (both stacks)
Python project configuration:
- Dependencies (Pulumi, AWS provider, Jinja2, pytest, ruff, mypy)
- Tool configuration (mypy strict mode, ruff rules)
- Python version requirement (>=3.14)

## Key Design Principles

1. **Pure-Python Helpers**: Network and template utilities avoid Pulumi imports for testability
2. **Cloud-Init Automation**: Complete instance bootstrap via cloud-init (no manual SSH setup)
3. **Snapshot-First Recovery**: Data persisted via scheduled EBS snapshots, not retained volumes
4. **Secrets Hygiene**: Secrets fetched from SSM Parameter Store at runtime, not persisted on disk
5. **Infrastructure as Code**: All resources defined in Pulumi (no manual AWS console changes)
6. **SSM-Only Access**: No SSH keys or open inbound ports; access via AWS Systems Manager
7. **Strict Type Checking**: mypy in strict mode for all Python code
8. **Testable Code**: Unit tests for all pure-Python logic
9. **Comprehensive Observability**: CloudWatch Dashboard with 20+ widgets for full stack visibility

## CloudWatch Dashboard

The stack automatically creates a comprehensive CloudWatch Dashboard named `openclaw-lab-observability` with the following widget categories:

### Dashboard Organization (8 Rows)

1. **Header & Status** (Row 1)
   - Instance metadata and stack information
   - EC2 status checks (instance and system)
   - Current CPU, memory, and disk usage (single value widgets)
   - Recent errors and warnings from CloudWatch Logs

2. **CPU Performance** (Row 2)
   - Stacked CPU usage breakdown (user, system, iowait, idle)
   - EC2 hypervisor CPU utilization (min/avg/max)
   - High CPU threshold annotations at 80%

3. **Memory Performance** (Row 3)
   - Memory usage percentages (used vs. available)
   - Absolute memory values in bytes
   - High memory threshold annotations at 80%

4. **Disk Usage** (Row 4)
   - Disk space usage for root (/) and data (/opt/openclaw) volumes
   - Inode usage tracking
   - EBS volume throughput (read/write bytes)
   - High disk usage threshold annotations at 80%

5. **Disk I/O Performance** (Row 5)
   - Disk I/O operations (read/write counts)
   - Disk I/O throughput (bytes)
   - Disk I/O time in milliseconds

6. **Network Performance** (Rows 6)
   - Network throughput (bytes sent/received)
   - Network packets sent/received
   - EC2 hypervisor network view
   - TCP connection states (established, time_wait)

7. **Systems Manager** (Row 7)
   - SSM command execution status (succeeded/failed/timed out)
   - Application and service logs via CloudWatch Logs Insights

8. **EBS & Spot Instance** (Row 8)
   - EBS volume operations (read/write ops)
   - EBS performance metrics (queue length, throughput %, consumed IOPS)
   - EBS volume idle time

### Accessing the Dashboard

```bash
# Get the dashboard URL from stack outputs
cd ec2-spot && pulumi stack output dashboard_url

# Open directly in browser (macOS)
open $(cd ec2-spot && pulumi stack output dashboard_url)
```

### Metrics Sources

- **CloudWatch Agent**: Custom metrics in `OpenClawLab/EC2` namespace
  - CPU: user, system, idle, iowait
  - Memory: used/available (% and bytes)
  - Disk: space usage, inodes
  - Disk I/O: operations, throughput, time
  - Network: bytes, packets, TCP states

- **AWS/EC2 Namespace**: Built-in EC2 metrics
  - CPU utilization (hypervisor view)
  - Network in/out
  - Status checks

- **AWS/EBS Namespace**: EBS volume metrics
  - Read/write operations and bytes
  - Queue length, idle time
  - Throughput percentage
  - Consumed IOPS

- **AWS/SSM Namespace**: Systems Manager metrics
  - Command execution status

- **CloudWatch Logs**: Log insights queries
  - Error and warning detection
  - Application log filtering

## Common File Modification Scenarios

### Adding a New Configuration Option
1. Add to `ec2-spot/__main__.py` config parsing section
2. Document default value and constraints
3. Update `ec2-spot/ARCHITECTURE.md` if it affects data/secret lifecycle
4. Update `README.md` if user-facing
5. Add validation and tests if logic is complex

### Modifying Cloud-Init Behavior
1. Update relevant template in `ec2-spot/templates/`
2. If using new context variables, update `user_data.py`
3. Test with `make ec2-spot-preview` to see rendered user-data
4. Validate with `make ec2-spot-deploy-logs` after deployment

### Adding a New IAM Permission
1. Identify which stack needs it (platform for GitHub Actions, ec2-spot for instance)
2. Add to appropriate IAM policy in `__main__.py`
3. Preview with `make platform-preview` or `make ec2-spot-preview`
4. Document in comments why the permission is needed

### Adding a New Makefile Command
1. Add target with `##` comment in appropriate section
2. Follow existing patterns for stack-specific commands
3. Test command works in isolation
4. Update `README.md` if command is user-facing

## File Dependencies

### EC2 Spot Stack Dependencies
- **Pulumi**: `pulumi`, `pulumi-aws`
- **Template Rendering**: `jinja2`
- **Testing**: `pytest`
- **Linting/Type Checking**: `ruff`, `mypy`
- **Platform Stack**: Cross-stack reference for ECR URL

### Platform Stack Dependencies
- **Pulumi**: `pulumi`, `pulumi-aws`
- **Linting/Type Checking**: `ruff`, `mypy`

### Runtime (on EC2 instance)
- **Amazon Linux 2023** (ARM64)
- **Docker** and **Docker Compose** (installed via cloud-init)
- **AWS CloudWatch Agent** (installed via cloud-init)
- **jq** (for JSON parsing in shell scripts)

## Version Control

### Tracked Files
All `.py`, `.yaml`, `.json`, `.md`, `.sh`, `.toml` files are tracked.

### Ignored Files
- `__pycache__/`: Python bytecode cache
- `.venv/`, `venv/`: Virtual environments
- `.env`: Local environment variables (NEVER commit secrets)
- `tmp/`: Temporary/scratch files
- `.mypy_cache/`, `.pytest_cache/`, `.ruff_cache/`: Tool caches

## Additional Resources

- [.github/WORKFLOWS.md](.github/WORKFLOWS.md): Detailed GitHub Actions workflow documentation
- [.github/copilot-instructions.md](.github/copilot-instructions.md): AI coding assistant guidelines
- [ec2-spot/ARCHITECTURE.md](ec2-spot/ARCHITECTURE.md): Architecture deep-dive and operational runbook
- [README.md](README.md): Project overview and quickstart

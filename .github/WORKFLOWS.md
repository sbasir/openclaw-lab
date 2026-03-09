# GitHub Actions Workflows

This repository includes automated CI/CD workflows for building and deploying OpenClaw Lab infrastructure on AWS.

## Workflows Overview

### 1. CI (`ci.yaml`)
**Triggers:** Push to `main`, Pull Requests  
**Runs on:** Changes to `ec2-spot/`, `platform/`, or `.github/workflows/ci.yaml`  
**Purpose:** Run linting and tests to ensure code quality

**Jobs:**
- **EC2 Spot:** Lint and test the EC2 Spot Pulumi infrastructure
  - Installs dependencies with `uv`
  - Runs linting checks
  - Runs unit tests
  
- **Platform:** Lint and test the Platform Pulumi infrastructure
  - Installs dependencies with `uv`
  - Runs linting checks
  - Runs unit tests

**No secrets required** - this workflow runs on all PRs

**Permissions:**
- `contents: read` (implicit)

### 2. Infra Preview (`infra-preview.yaml`)
**Triggers:** Push to `main`, Pull Requests, Manual workflow dispatch  
**Runs on:** Changes to `ec2-spot/`, `platform/`, or `.github/workflows/infra-preview.yaml`  
**Purpose:** Preview infrastructure changes before deployment

**Jobs:** Matrix strategy — runs both EC2 Spot and Platform previews **for every active stack** in parallel.

| Matrix entry | Stack | GitHub Environment |
|---|---|---|
| EC2 Spot / Platform preview | `dev.uae` | `uae` |
| EC2 Spot / Platform preview | `dev.mumbai` | `mumbai` |

`fail-fast: false` ensures a downed region doesn't cancel the other.

Each matrix job reads credentials from the matching **GitHub Environment** (see [GitHub Environments](#github-environments)):
- `secrets.AWS_ROLE_ARN` — region-specific IAM role ARN
- `vars.AWS_REGION` — region for that environment
- `secrets.PULUMI_ACCESS_TOKEN` — Pulumi Cloud access token (shared)

**Permissions:**
- `id-token: write` - Required for AWS OIDC
- `contents: read`
- `pull-requests: write` - To post preview comments

### 3. Infra Up (`infra-up.yaml`)
**Triggers:** Manual workflow dispatch  
**Purpose:** Deploy infrastructure changes to AWS for a selected region

**Input:**
- `stack` (choice, default `dev.uae`) — the Pulumi stack to deploy. Options: `dev.uae`, `dev.mumbai`

**Jobs:**
- **EC2 Spot:** Deploys EC2 Spot infrastructure for the selected stack
- **Platform:** Deploys Platform infrastructure for the selected stack

The GitHub Environment is resolved from the `stack` input (`dev.uae` → `uae`, `dev.mumbai` → `mumbai`), which supplies region-specific `AWS_ROLE_ARN` and `AWS_REGION`.

Requires:
- `secrets.AWS_ROLE_ARN` — from selected GitHub Environment
- `secrets.PULUMI_ACCESS_TOKEN` — Pulumi Cloud access token
- `vars.AWS_REGION` — from selected GitHub Environment

**Permissions:**
- `id-token: write` - Required for AWS OIDC
- `contents: read`

### 4. Infra Destroy (`infra-destroy.yaml`)
**Triggers:** Manual workflow dispatch  
**Purpose:** Destroy `ec2-spot` infrastructure for a selected region

⚠️ **Warning:** This will permanently delete `ec2-spot` resources (EC2 instance, networking resources, EIP associations, and attached stack-managed resources) for the selected region. Platform resources are managed separately.

**Input:**
- `stack` (choice, default `dev.uae`) — the Pulumi stack to destroy. Options: `dev.uae`, `dev.mumbai`

The GitHub Environment is resolved from the `stack` input, same as Infra Up.

Requires:
- `secrets.AWS_ROLE_ARN` — from selected GitHub Environment
- `secrets.PULUMI_ACCESS_TOKEN` — Pulumi Cloud access token
- `vars.AWS_REGION` — from selected GitHub Environment

**Permissions:**
- `id-token: write` - Required for AWS OIDC
- `contents: read`

### 5. Build and Push OpenClaw Docker Image (`build-push-image.yaml`)
**Triggers:** Manual workflow dispatch  
**Purpose:** Build the OpenClaw Docker image and push to ECR in all active regions

**Jobs:** Matrix strategy — one job per active stack, each authenticating to its own region's ECR.

| Matrix entry | Stack | GitHub Environment |
|---|---|---|
| Build & push | `dev.uae` | `uae` |
| Build & push | `dev.mumbai` | `mumbai` |

**Process (per region):**
1. Checks out this repository and the OpenClaw repository
2. Retrieves ECR repository URL from that region's Platform Pulumi stack output
3. Authenticates to that region's ECR via AWS OIDC
4. Builds and pushes the ARM64 image to ECR (GHA cache scoped per stack)

Requires (from each GitHub Environment):
- `secrets.AWS_ROLE_ARN` — region-specific IAM role ARN
- `secrets.PULUMI_ACCESS_TOKEN` — Pulumi Cloud access token
- `vars.AWS_REGION` — region for that environment

**Permissions:**
- `id-token: write` - Required for AWS OIDC
- `contents: read`

## Setup Instructions

### 1. Configure AWS OIDC Provider

Create an OIDC identity provider in AWS IAM (one-time per AWS account):

```bash
# Create the OIDC provider (one-time setup)
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### 2. Create IAM Role for GitHub Actions

This role is created in the `platform` Pulumi stack. It allows GitHub Actions to assume it via OIDC and perform deployments.
There is a chicken and egg problem where the role needs to exist before the workflow can run, but the workflow is needed to create the role. To resolve this, you need to deploy the Platform stack first using the Pulumi CLI:
1. Set up AWS credentials locally (e.g., via `aws configure` or environment variables)
2. Install Pulumi CLI and dependencies
3. Deploy the Platform stack for each region to create the IAM roles:
   ```bash
   cd platform
   pulumi stack select dev.uae && pulumi up    # UAE / me-central-1
   pulumi stack select dev.mumbai && pulumi up # Mumbai / ap-south-1
   ```

### 3. Create GitHub Environments

Each deployment region requires a dedicated [GitHub Environment](https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment) that stores region-specific credentials. Workflows select the correct environment automatically based on the target stack.

#### Current Environments

| Environment | Stack | AWS Region |
|-------------|-------|------------|
| `uae` | `dev.uae` | `me-central-1` |
| `mumbai` | `dev.mumbai` | `ap-south-1` |

#### Create Environments via GitHub CLI

```bash
# Create 'uae' environment and configure it
gh api repos/{owner}/{repo}/environments/uae --method PUT --input /dev/null
gh secret set AWS_ROLE_ARN --env uae --body "<role ARN from: cd platform && pulumi stack select dev.uae && pulumi stack output github_actions_role_arn>"
gh variable set AWS_REGION --env uae --body "me-central-1"

# Create 'mumbai' environment and configure it
gh api repos/{owner}/{repo}/environments/mumbai --method PUT --input /dev/null
gh secret set AWS_ROLE_ARN --env mumbai --body "<role ARN from: cd platform && pulumi stack select dev.mumbai && pulumi stack output github_actions_role_arn>"
gh variable set AWS_REGION --env mumbai --body "ap-south-1"
```

Or via **GitHub web interface**: Settings → Environments → New environment → add secrets/variables per environment.

#### Per-Environment Values

| Name | Type | Description | How to get |
|------|------|-------------|-----------|
| `AWS_ROLE_ARN` | Secret | IAM role ARN for OIDC | `cd platform && pulumi stack output github_actions_role_arn` |
| `AWS_REGION` | Variable | AWS region | `me-central-1`, `ap-south-1`, etc. |

#### Shared (Repository-level)

| Name | Type | Description |
|------|------|-------------|
| `PULUMI_ACCESS_TOKEN` | Secret | Pulumi Cloud access token — get from [Pulumi Console](https://app.pulumi.com/account/tokens) |

#### Adding a New Region

1. Create a new `Pulumi.dev.<alias>.yaml` in both `platform/` and `ec2-spot/` dirs
2. Add the stack to the workflow matrix in `infra-preview.yaml` and `build-push-image.yaml`, and to the choice options in `infra-up.yaml` / `infra-destroy.yaml`
3. Deploy the platform stack locally to get the role ARN
4. Create a new GitHub Environment and populate `AWS_ROLE_ARN` and `AWS_REGION`

### 4. Initialize Pulumi Stacks

If stacks don't exist, create them:

#### Local
```bash
# Deploy ec2-spot and platform for UAE
cd ec2-spot && pulumi stack select dev.uae && pulumi up
cd ../platform && pulumi stack select dev.uae && pulumi up

# Deploy ec2-spot and platform for Mumbai
cd ec2-spot && pulumi stack select dev.mumbai && pulumi up
cd ../platform && pulumi stack select dev.mumbai && pulumi up
```

### 5. Configure Environment Protection (Optional but Recommended)

For additional security on infrastructure deployments:

1. Go to repository Settings → Environments
2. Select each environment (`uae`, `mumbai`)
3. Configure protection rules:
   - Required reviewers (recommended: 1+ people)
   - Deployment branches (restrict to `main` only)

## Usage Examples

### Run CI Tests Locally

Test linting and unit tests before pushing:

```bash
# Test EC2 Spot module
make lint-ec2-spot
make test-ec2-spot

# Test Platform module
make lint-platform
make test-platform

# Or test everything
make ci
```

### Preview Infrastructure Changes

1. Create a PR with infrastructure changes to `ec2-spot/` or `platform/`
2. The `Infra Preview` workflow automatically runs
3. Review the Pulumi preview output in the workflow logs
4. View comments on the PR with preview details (if available)
5. Merge the PR to `main` after approval

### Deploy Infrastructure

1. Go to Actions → "Infra Up" workflow
2. Click "Run workflow"
3. Select the target stack (`dev.uae` or `dev.mumbai`)
4. Wait for both EC2 Spot and Platform deployments to complete
5. Verify resources in AWS Console:
   - EC2 instances in EC2 dashboard (check the target region)
   - Container image in ECR
   - Application logs in CloudWatch

### Destroy Infrastructure

⚠️ **Warning:** This destroys `ec2-spot` resources for the selected stack.

1. Go to Actions → "Infra Destroy" workflow
2. Click "Run workflow"
3. Select the target stack (`dev.uae` or `dev.mumbai`)
4. All EC2 Spot resources for that region will be deleted
5. Pulumi state will be preserved in Pulumi Cloud

**Post-destruction:**
- All EC2 instances will be terminated
- Elastic IPs will be released
- Security groups will be deleted
- IAM roles will be removed

### Build and Push Docker Image

1. Ensure the Platform stack is deployed in all active regions (has ECR repositories)
2. Go to Actions → "Build and Push OpenClaw Docker Image" workflow
3. Click "Run workflow"
4. Workflow runs a matrix job per region — builds the ARM64 image and pushes to each region's ECR
5. Verify the images in AWS ECR Console (check each region)

### Test Workflows Locally

Test workflows locally before pushing using `act`:

```bash
# Test CI workflow
make gh-act-ci

# Test Infra Preview (requires AWS credentials)
make gh-act-infra-preview STACK=dev.uae

# Test Infra Up (requires AWS credentials)
make gh-act-infra-up STACK=dev.uae

# Test Infra Destroy (requires AWS credentials)
make gh-act-infra-destroy STACK=dev.uae
```

## Security Best Practices

1. **Secrets Management**
   - Never commit secrets to the repository
   - Use GitHub Secrets for sensitive data
   - Use GitHub Variables for non-sensitive configuration
   - Rotate secrets regularly
   - Review secret access in audit logs

2. **OIDC Authentication**
   - Use AWS OIDC instead of long-lived IAM credentials
   - Reduces risk of credential exposure
   - Credentials are short-lived and environment-specific
   - Verify the trust policy includes only your repository

3. **Least Privilege Permissions**
   - Limit IAM role permissions to minimum required
   - Review and audit IAM policies regularly
   - Separate EC2 and Platform deployments if needed
   - Use resource-specific ARNs in policies

4. **Access Control**
   - Enable branch protection on `main`
   - Require code reviews for PRs
   - Enable environment protection for production deployments
   - Limit who can trigger manual workflows

5. **Audit Logging**
   - Monitor CloudTrail for AWS API calls
   - Review GitHub Actions logs for suspicious activity
   - Enable GitHub secret scanning with push protection
   - Archive workflow logs for compliance

## Troubleshooting

### Workflow fails with "OIDC authentication failed"

**Symptoms:** Error message about `sts:AssumeRoleWithWebIdentity`

**Solutions:**
1. Verify `AWS_ROLE_ARN` secret is correct
2. Check IAM role trust policy includes your repository:
   ```
   repo:GITHUB_ORG/openclaw-lab:*
   ```
3. Verify OIDC provider exists in AWS IAM
4. Ensure the principal ARN in trust policy matches your AWS account

### Pulumi preview/up fails with authentication error

**Symptoms:** "Unable to authenticate to Pulumi Cloud" or similar

**Solutions:**
1. Verify `PULUMI_ACCESS_TOKEN` secret is valid
2. Ensure token hasn't expired (regenerate from Pulumi Console if needed)
3. Check Pulumi stacks exist:
   ```bash
   cd ec2-spot && pulumi stack ls
   cd ../platform && pulumi stack ls
   ```
4. Verify token has access to the organization/project in Pulumi Cloud

### Pulumi preview/up fails with AWS permission error

**Symptoms:** "AccessDenied" or permission-related errors

**Solutions:**
1. Verify IAM role has required permissions:
   - `AmazonEC2FullAccess`
   - `AmazonECRFullAccess`
   - `IAMFullAccess`
   - `AmazonSSMFullAccess`
2. Check CloudTrail for specific failing API calls
3. Verify the role is being assumed correctly: check workflow logs for `aws sts get-caller-identity`
4. Test locally:
   ```bash
   aws sts assume-role-with-web-identity \
     --role-arn $AWS_ROLE_ARN \
     --role-session-name test \
     --web-identity-token $OIDC_TOKEN
   ```

### Docker image build fails

**Symptoms:** "Error building Docker image" or similar

**Solutions:**
1. Verify the OpenClaw repository URL is correct
2. Check the Dockerfile is present in the OpenClaw repository
3. Ensure ECR repository exists (Platform stack must be deployed first)
4. Verify AWS credentials have `AmazonECRFullAccess` permission
5. Check disk space on runner (GitHub-hosted runners have ~14GB available)

### CI tests fail but pass locally

**Symptoms:** Linting or tests pass on local machine but fail in CI

**Solutions:**
1. Check Python version matches:
   ```bash
   python3 --version
   # Compare with workflows/ci.yaml
   ```
2. Verify all dependencies installed:
   ```bash
   make install-ec2-spot
   make install-platform
   ```
3. Clear cache in GitHub Actions settings if dependencies changed
4. Check for environment-specific issues:
   - File path separators (Windows vs Unix)
   - Environment variables
   - Temporary file locations

### Workflow job runs on wrong runner

**Symptoms:** "No suitable runners found" or similar

**Solutions:**
1. Verify `runs-on: ubuntu-latest` is set in workflow
2. Check if self-hosted runners were configured
3. For local testing with `act`:
   - Verify Docker is running
   - Update platform: `make gh-act-update-platform`
   - Check `ACT_FLAGS` in Makefile

## Workflow Versions

All workflows use pinned versions of GitHub Actions for security and stability:

- `actions/checkout@v6` - Check out repository code
- `actions/setup-python@v6` - Set up Python runtime (if needed)
- `actions/cache@v5` - Cache dependencies
- `aws-actions/configure-aws-credentials@v6` - Configure AWS credentials via OIDC
- `pulumi/actions@v6` - Run Pulumi commands
- `astral-sh/setup-uv@v7` - Set up uv Python package manager
- `docker/setup-qemu-action@v3` - Set up QEMU for multi-platform builds
- `docker/setup-buildx-action@v3` - Set up Docker Buildx

These are pinned to major versions and updated via Dependabot. Review updates carefully before merging.

## Additional Resources

- [Pulumi Documentation](https://www.pulumi.com/docs/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [AWS OIDC Configuration](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/about-security-hardening-with-openid-connect)
- [GitHub Secrets Best Practices](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions)

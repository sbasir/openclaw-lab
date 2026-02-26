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

**Jobs:**
- **EC2 Spot Preview:** Shows Pulumi preview for EC2 Spot infrastructure
- **Platform Preview:** Shows Pulumi preview for Platform infrastructure

Requires secrets:
- `AWS_ROLE_ARN` - AWS IAM role ARN for OIDC authentication
- `PULUMI_ACCESS_TOKEN` - Pulumi Cloud access token

Requires variables:
- `AWS_REGION` - AWS region for deployment (e.g., `us-east-1`)

**Permissions:**
- `id-token: write` - Required for AWS OIDC
- `contents: read`
- `pull-requests: write` - To post preview comments

### 3. Infra Up (`infra-up.yaml`)
**Triggers:** Manual workflow dispatch  
**Purpose:** Deploy infrastructure changes to AWS

**Jobs:**
- **EC2 Spot:** Deploys EC2 Spot infrastructure using Pulumi
- **Platform:** Deploys Platform infrastructure using Pulumi

Requires secrets:
- `AWS_ROLE_ARN` - AWS IAM role ARN for OIDC authentication
- `PULUMI_ACCESS_TOKEN` - Pulumi Cloud access token

Requires variables:
- `AWS_REGION` - AWS region for deployment (e.g., `us-east-1`)

**Permissions:**
- `id-token: write` - Required for AWS OIDC
- `contents: read`

### 4. Infra Destroy (`infra-destroy.yaml`)
**Triggers:** Manual workflow dispatch  
**Purpose:** Destroy `ec2-spot` infrastructure resources

⚠️ **Warning:** This will permanently delete `ec2-spot` resources (EC2 instance, networking resources, EIP associations, and attached stack-managed resources). Platform resources are managed separately.

Requires secrets:
- `AWS_ROLE_ARN` - AWS IAM role ARN for OIDC authentication
- `PULUMI_ACCESS_TOKEN` - Pulumi Cloud access token

Requires variables:
- `AWS_REGION` - AWS region for deployment (e.g., `us-east-1`)

**Permissions:**
- `id-token: write` - Required for AWS OIDC
- `contents: read`

### 5. Build and Push OpenClaw Docker Image (`build-push-image.yaml`)
**Triggers:** Manual workflow dispatch  
**Purpose:** Build the OpenClaw Docker image and push to ECR

**Process:**
1. Checks out this repository and the OpenClaw repository
2. Retrieves ECR repository URL from the Platform Pulumi stack output
3. Authenticates to ECR via AWS OIDC
4. Builds the OpenClaw Docker image for ARM64 architecture
5. Tags and pushes the image to ECR

Requires secrets:
- `AWS_ROLE_ARN` - AWS IAM role ARN for OIDC authentication
- `PULUMI_ACCESS_TOKEN` - Pulumi Cloud access token

Requires variables:
- `AWS_REGION` - AWS region for deployment (e.g., `us-east-1`)

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
3. Deploy the Platform stack to create the IAM role:
   ```bash
   make platform-up
   ```

### 3. Configure GitHub Secrets and Variables

** Browser **
Go to repository settings → Secrets and variables → Actions

** GitHub CLI **
```bash
# Add secrets
gh secret set <Secret Name> -r <Repo Org>/<Repo Name> --body "<Secret Value>"
# Add variables
gh variable set <Variable Name> -r <Repo Org>/<Repo Name> --body "<Variable Value>"
```

#### Secrets

Add the following secrets:

| Secret Name | Description | How to get |
|-------------|-------------|-----------|
| `AWS_ROLE_ARN` | IAM role ARN for OIDC | `arn:aws:iam::123456789012:role/github-actions-role` |
| `PULUMI_ACCESS_TOKEN` | Pulumi Cloud access token | Get from [Pulumi Console](https://app.pulumi.com/account/tokens) |

#### Variables

Add the following repository variables:

| Variable Name | Description | Example |
|---------------|-------------|---------|
| `AWS_REGION` | AWS region for deployment | `us-east-1` |

### 4. Initialize Pulumi Stacks

If stacks don't exist, create them:

#### Local
```bash
# Create/deploy ec2-spot stack
make ec2-spot-up

# Create/deploy platform stack
make platform-up
```

### 5. Configure Environment Protection (Optional but Recommended)

For additional security on infrastructure deployments:

1. Go to repository Settings → Environments
2. Click "New environment" and name it `production`
3. Configure protection rules:
   - Required reviewers (recommended: 1+ people)
   - Wait timer (recommended: 24 hours)
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
3. Wait for both EC2 Spot and Platform deployments to complete
4. Verify resources in AWS Console:
   - EC2 instances in EC2 dashboard
   - Container image in ECR
   - Application logs in CloudWatch

### Destroy Infrastructure

⚠️ **Warning:** This destroys `ec2-spot` resources for the selected stack.

1. Go to Actions → "Infra Destroy" workflow
2. Click "Run workflow"
3. All EC2 Spot resources will be deleted
4. Pulumi state will be preserved in Pulumi Cloud

**Post-destruction:**
- All EC2 instances will be terminated
- Elastic IPs will be released
- Security groups will be deleted
- IAM roles will be removed

### Build and Push Docker Image

1. Ensure the Platform stack is deployed (has ECR repository)
2. Go to Actions → "Build and Push OpenClaw Docker Image" workflow
3. Click "Run workflow"
4. Workflow will:
   - Clone the OpenClaw repository
   - Build the Docker image for ARM64
   - Push to ECR
5. Verify the image in AWS ECR Console

### Test Workflows Locally

Test workflows locally before pushing using `act`:

```bash
# Test CI workflow
make gh-act-ci

# Test Infra Preview (requires AWS credentials)
make gh-act-infra-preview STACK=dev

# Test Infra Up (requires AWS credentials)
make gh-act-infra-up STACK=dev

# Test Infra Destroy (requires AWS credentials)
make gh-act-infra-destroy STACK=dev
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

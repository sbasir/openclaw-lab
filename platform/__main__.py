"""Platform resources (GitHub OIDC role, ECR) for openclaw-lab.

This stack manages long-lived platform infrastructure that the ec2-spot stack
and CI/CD pipelines depend on:
  - GitHub Actions OIDC provider and IAM role for deploying via Pulumi
  - Private ECR repository for the OpenClaw Docker image

The platform stack should be deployed BEFORE the ec2-spot stack, as it provides
the ECR repository URL that ec2-spot references via StackReference.
"""

import json

import pulumi
import pulumi_aws as aws

prefix = "openclaw-platform"
config = pulumi.Config()

# GitHub repository that is allowed to assume the deploy role.
# Configurable so forks can override it.
# pulumi config set github_repo sbasir/openclaw-lab
github_repo = config.get("github_repo")

if not github_repo:
    raise ValueError(
        "github_repo config value is required (e.g. 'sbasir/openclaw-lab')"
    )

account_id = aws.get_caller_identity().account_id
aws_region = aws.get_region().region

# =============================================================================
# GitHub Actions OIDC Provider
# =============================================================================

# AWS allows only one OIDC provider per issuer URL per account.  If the GitHub
# OIDC provider already exists (common when multiple repos share it), we look
# it up instead of creating a duplicate.
#
# Set `create_oidc_provider` to "true" in stack config if this is the first
# time setting up GitHub OIDC in the account:
#   pulumi config set create_oidc_provider true
create_oidc_provider = config.get_bool("create_oidc_provider") or False

GITHUB_OIDC_URL = "https://token.actions.githubusercontent.com"

if create_oidc_provider:
    oidc_provider = aws.iam.OpenIdConnectProvider(
        f"{prefix}-github-oidc",
        url=GITHUB_OIDC_URL,
        client_id_lists=["sts.amazonaws.com"],
        # AWS ignores the thumbprint for GitHub's OIDC provider, but the
        # field is required.  Using the well-known placeholder value.
        thumbprint_lists=["ffffffffffffffffffffffffffffffffffffffff"],
        tags={"Name": f"{prefix}-github-oidc"},
    )
    oidc_provider_arn = oidc_provider.arn
else:
    # Look up the existing provider by URL.
    existing = aws.iam.get_open_id_connect_provider(url=GITHUB_OIDC_URL)
    oidc_provider_arn = pulumi.Output.from_input(existing.arn)

# =============================================================================
# IAM Role for GitHub Actions
# =============================================================================

# Trust policy: only tokens from the configured repo can assume this role.
assume_role_policy = oidc_provider_arn.apply(
    lambda arn: json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Federated": arn},
                    "Action": "sts:AssumeRoleWithWebIdentity",
                    "Condition": {
                        "StringEquals": {
                            "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                        },
                        "StringLike": {
                            "token.actions.githubusercontent.com:sub": f"repo:{github_repo}:*",
                        },
                    },
                }
            ],
        }
    )
)

github_actions_role = aws.iam.Role(
    f"{prefix}-github-actions-role",
    assume_role_policy=assume_role_policy,
    description=f"GitHub Actions deploy role for {github_repo}",
    tags={"Name": f"{prefix}-github-actions-role"},
)

# ---------------------------------------------------------------------------
# Permissions for the ec2-spot Pulumi stack
# ---------------------------------------------------------------------------
# Scoped to the specific services and resource patterns used by ec2-spot.

# EC2 permissions: VPC, subnets, IGW, route tables, security groups, spot
# instances, EIPs, AMI lookups, spot price lookups, AZ lookups, tags, IPv6.
ec2_policy = aws.iam.RolePolicy(
    f"{prefix}-ec2-policy",
    role=github_actions_role.name,
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "EC2FullForOpenClaw",
                    "Effect": "Allow",
                    "Action": [
                        # General Read permissions (needed for lookups and some actions)
                        "ec2:Describe*",
                        # VPC and networking
                        "ec2:CreateVpc",
                        "ec2:DeleteVpc",
                        "ec2:ModifyVpcAttribute",
                        "ec2:CreateSubnet",
                        "ec2:DeleteSubnet",
                        "ec2:CreateInternetGateway",
                        "ec2:DeleteInternetGateway",
                        "ec2:AttachInternetGateway",
                        "ec2:DetachInternetGateway",
                        "ec2:CreateRouteTable",
                        "ec2:DeleteRouteTable",
                        "ec2:CreateRoute",
                        "ec2:DeleteRoute",
                        "ec2:ReplaceRoute",
                        "ec2:AssociateRouteTable",
                        "ec2:DisassociateRouteTable",
                        # Security groups
                        "ec2:CreateSecurityGroup",
                        "ec2:DeleteSecurityGroup",
                        "ec2:AuthorizeSecurityGroupEgress",
                        "ec2:AuthorizeSecurityGroupIngress",
                        "ec2:RevokeSecurityGroupEgress",
                        "ec2:RevokeSecurityGroupIngress",
                        # EC2 / Spot instances
                        "ec2:RequestSpotInstances",
                        "ec2:CancelSpotInstanceRequests",
                        "ec2:TerminateInstances",
                        "ec2:StopInstances",
                        "ec2:StartInstances",
                        "ec2:RunInstances",
                        # EIP
                        "ec2:AllocateAddress",
                        "ec2:ReleaseAddress",
                        "ec2:AssociateAddress",
                        "ec2:DisassociateAddress",
                        # Tags
                        "ec2:CreateTags",
                        "ec2:DeleteTags",
                        # IPv6
                        "ec2:AssociateVpcCidrBlock",
                        "ec2:DisassociateVpcCidrBlock",
                        "ec2:AssociateSubnetCidrBlock",
                        "ec2:DisassociateSubnetCidrBlock",
                        "ec2:ModifySubnetAttribute",
                    ],
                    "Resource": "*",
                },
            ],
        }
    ),
)

# IAM permissions: manage the EC2 instance role, policies, and instance profile.
iam_policy = aws.iam.RolePolicy(
    f"{prefix}-iam-policy",
    role=github_actions_role.name,
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "IAMManageOpenClawRoles",
                    "Effect": "Allow",
                    "Action": [
                        "iam:CreateRole",
                        "iam:DeleteRole",
                        "iam:GetRole",
                        "iam:UpdateRole",
                        "iam:TagRole",
                        "iam:UntagRole",
                        "iam:ListRoleTags",
                        "iam:PutRolePolicy",
                        "iam:GetRolePolicy",
                        "iam:DeleteRolePolicy",
                        "iam:ListRolePolicies",
                        "iam:AttachRolePolicy",
                        "iam:DetachRolePolicy",
                        "iam:ListAttachedRolePolicies",
                        "iam:CreateInstanceProfile",
                        "iam:DeleteInstanceProfile",
                        "iam:GetInstanceProfile",
                        "iam:AddRoleToInstanceProfile",
                        "iam:RemoveRoleFromInstanceProfile",
                        "iam:TagInstanceProfile",
                        "iam:UntagInstanceProfile",
                        "iam:ListInstanceProfileTags",
                        "iam:ListInstanceProfilesForRole",
                        "iam:PassRole",
                    ],
                    "Resource": [
                        f"arn:aws:iam::{account_id}:role/openclaw-lab-*",
                        f"arn:aws:iam::{account_id}:instance-profile/openclaw-lab-*",
                    ],
                },
            ],
        }
    ),
)

# OIDC permissions: allow listing and reading the OIDC provider.
# This is needed by Pulumi to verify the provider exists and get its ARN.
# Note: This permission is only usable AFTER the role exists. The platform stack
# must be initially deployed locally (not via GitHub Actions) to bootstrap the role.
iam_oidc_policy = aws.iam.RolePolicy(
    f"{prefix}-iam-oidc-policy",
    role=github_actions_role.name,
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "IAMRoleForOIDC",
                    "Effect": "Allow",
                    "Action": [
                        "iam:GetOpenIDConnectProvider",
                        "iam:ListOpenIDConnectProviders",
                    ],
                    "Resource": f"arn:aws:iam::{account_id}:oidc-provider/*",
                },
            ],
        }
    ),
)

# SSM permissions: parameter store access and send-command for deployments.
ssm_policy = aws.iam.RolePolicy(
    f"{prefix}-ssm-policy",
    role=github_actions_role.name,
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "SSMParameterStore",
                    "Effect": "Allow",
                    "Action": [
                        "ssm:GetParameter",
                        "ssm:PutParameter",
                        "ssm:GetParameters",
                        "ssm:GetParametersByPath",
                    ],
                    "Resource": f"arn:aws:ssm:*:{account_id}:parameter/openclaw-lab/*",
                },
                {
                    "Sid": "SSMSendCommand",
                    "Effect": "Allow",
                    "Action": [
                        "ssm:SendCommand",
                    ],
                    "Resource": [
                        f"arn:aws:ec2:*:{account_id}:instance/*",
                        "arn:aws:ssm:*::document/AWS-RunShellScript",
                    ],
                },
                {
                    "Sid": "SSMGetCommandInvocation",
                    "Effect": "Allow",
                    "Action": [
                        "ssm:GetCommandInvocation",
                    ],
                    "Resource": f"arn:aws:ssm:*:{account_id}:*",
                },
            ],
        }
    ),
)

# S3 permissions: manage the OpenClaw backup bucket created in this stack.
s3_platform_policy = aws.iam.RolePolicy(
    f"{prefix}-s3-platform-policy",
    role=github_actions_role.name,
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "S3BackupBucketManagement",
                    "Effect": "Allow",
                    "Action": [
                        "s3:CreateBucket",
                        "s3:DeleteBucket",
                        "s3:ListBucket",
                        "s3:GetBucketLocation",
                        "s3:GetBucketTagging",
                        "s3:PutBucketTagging",
                        "s3:GetBucketEncryption",
                        "s3:PutBucketEncryption",
                        "s3:GetBucketPublicAccessBlock",
                        "s3:PutBucketPublicAccessBlock",
                        "s3:PutBucketVersioning",
                        "s3:GetBucketVersioning",
                    ],
                    "Resource": [
                        "arn:aws:s3:::openclaw-lab-backup-*",
                        "arn:aws:s3:::openclaw-lab-backup-*/*",
                    ],
                }
            ],
        }
    ),
)

# STS permissions: Pulumi uses get-caller-identity to determine the account.
sts_policy = aws.iam.RolePolicy(
    f"{prefix}-sts-policy",
    role=github_actions_role.name,
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "STSGetCallerIdentity",
                    "Effect": "Allow",
                    "Action": "sts:GetCallerIdentity",
                    "Resource": "*",
                },
            ],
        }
    ),
)

# ECR permissions: push/pull images
ecr_policy_attachment = aws.iam.RolePolicyAttachment(
    f"{prefix}-ecr-policy",
    role=github_actions_role.name,
    policy_arn="arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser",
)

# EC2 Volume permissions: manage EBS volumes for persistent storage.
ec2_volume_policy = aws.iam.RolePolicy(
    f"{prefix}-ec2-volume-policy",
    role=github_actions_role.name,
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "EC2VolumeManagement",
                    "Effect": "Allow",
                    "Action": [
                        "ec2:CreateVolume",
                        "ec2:DeleteVolume",
                        "ec2:AttachVolume",
                        "ec2:DetachVolume",
                        "ec2:DescribeVolumes",
                    ],
                    "Resource": [
                        f"arn:aws:ec2:{aws_region}:{account_id}:volume/*",
                        f"arn:aws:ec2:{aws_region}:{account_id}:instance/*",
                    ],
                },
                {
                    "Sid": "EC2SnapshotManagement",
                    "Effect": "Allow",
                    "Action": [
                        "ec2:CreateSnapshot",
                        "ec2:DeleteSnapshot",
                        "ec2:DescribeSnapshots",
                        "ec2:CreateTags",
                    ],
                    "Resource": "*",
                },
            ],
        }
    ),
)

# DLM permissions: manage Data Lifecycle Manager policies for EBS snapshots.
dlm_policy = aws.iam.RolePolicy(
    f"{prefix}-dlm-policy",
    role=github_actions_role.name,
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "DLMImageManagement",
                    "Effect": "Allow",
                    "Action": [
                        "dlm:GetLifecyclePolicies",
                        "dlm:CreateLifecyclePolicy",
                        "dlm:DeleteLifecyclePolicy",
                        "dlm:GetLifecyclePolicy",
                        "dlm:UpdateLifecyclePolicy",
                        "dlm:ListTagsForResource",
                        "dlm:TagResource",
                    ],
                    "Resource": f"arn:aws:dlm:{aws_region}:{account_id}:policy/*",
                },
            ],
        }
    ),
)

# CloudWatch permissions: manage CloudWatch Dashboards for observability.
cloudwatch_policy = aws.iam.RolePolicy(
    f"{prefix}-cloudwatch-policy",
    role=github_actions_role.name,
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "CloudWatchDashboardManagement",
                    "Effect": "Allow",
                    "Action": [
                        "cloudwatch:PutDashboard",
                        "cloudwatch:GetDashboard",
                        "cloudwatch:DeleteDashboards",
                        "cloudwatch:ListDashboards",
                    ],
                    "Resource": "*",
                },
            ],
        }
    ),
)

# =============================================================================
# Private ECR Repository
# =============================================================================

ecr_repo = aws.ecr.Repository(
    f"{prefix}-ecr",
    name="openclaw",
    image_tag_mutability="MUTABLE",
    force_delete=True,
    tags={"Name": f"{prefix}-ecr"},
)

# =============================================================================
# S3 Backup Bucket
# =============================================================================

s3_backup_bucket_name = f"openclaw-lab-backup-{pulumi.get_stack()}-{account_id}".lower()

s3_backup_bucket = aws.s3.Bucket(
    f"{prefix}-backup-bucket",
    bucket=s3_backup_bucket_name,
    force_destroy=False,
    server_side_encryption_configuration={
        "rule": {
            "apply_server_side_encryption_by_default": {
                "sse_algorithm": "AES256",
            },
        },
    },
    tags={"Name": f"{prefix}-backup-bucket"},
)

aws.s3.BucketPublicAccessBlock(
    f"{prefix}-backup-bucket-public-access",
    bucket=s3_backup_bucket.id,
    block_public_acls=True,
    block_public_policy=True,
    ignore_public_acls=True,
    restrict_public_buckets=True,
)

# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

pulumi.export("github_actions_role_arn", github_actions_role.arn)
pulumi.export("oidc_provider_arn", oidc_provider_arn)
pulumi.export("ecr_repository_url", ecr_repo.repository_url)
pulumi.export("s3_backup_bucket_name", s3_backup_bucket.bucket)
pulumi.export("s3_backup_bucket_arn", s3_backup_bucket.arn)

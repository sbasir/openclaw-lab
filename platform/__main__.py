"""Platform resources (GitHub OIDC role, ECR) for openclaw-lab.

This stack manages long-lived platform infrastructure that the ec2-spot stack
and CI/CD pipelines depend on:
  - GitHub Actions OIDC provider and IAM role for deploying via Pulumi
  - Public ECR repository for the OpenClaw Docker image
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
# instances, EIPs, AMI lookups, spot price lookups, AZ lookups, tags.
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
                        # VPC and networking
                        "ec2:CreateVpc",
                        "ec2:DeleteVpc",
                        "ec2:DescribeVpcs",
                        "ec2:ModifyVpcAttribute",
                        "ec2:CreateSubnet",
                        "ec2:DeleteSubnet",
                        "ec2:DescribeSubnets",
                        "ec2:CreateInternetGateway",
                        "ec2:DeleteInternetGateway",
                        "ec2:AttachInternetGateway",
                        "ec2:DetachInternetGateway",
                        "ec2:DescribeInternetGateways",
                        "ec2:CreateRouteTable",
                        "ec2:DeleteRouteTable",
                        "ec2:DescribeRouteTables",
                        "ec2:CreateRoute",
                        "ec2:DeleteRoute",
                        "ec2:ReplaceRoute",
                        "ec2:AssociateRouteTable",
                        "ec2:DisassociateRouteTable",
                        # Security groups
                        "ec2:CreateSecurityGroup",
                        "ec2:DeleteSecurityGroup",
                        "ec2:DescribeSecurityGroups",
                        "ec2:DescribeSecurityGroupRules",
                        "ec2:AuthorizeSecurityGroupEgress",
                        "ec2:AuthorizeSecurityGroupIngress",
                        "ec2:RevokeSecurityGroupEgress",
                        "ec2:RevokeSecurityGroupIngress",
                        # Spot instances
                        "ec2:RequestSpotInstances",
                        "ec2:CancelSpotInstanceRequests",
                        "ec2:DescribeSpotInstanceRequests",
                        "ec2:DescribeSpotPriceHistory",
                        "ec2:DescribeInstances",
                        "ec2:TerminateInstances",
                        "ec2:StopInstances",
                        "ec2:StartInstances",
                        "ec2:RunInstances",
                        # EIP
                        "ec2:AllocateAddress",
                        "ec2:ReleaseAddress",
                        "ec2:AssociateAddress",
                        "ec2:DisassociateAddress",
                        "ec2:DescribeAddresses",
                        # AMI and AZ lookups
                        "ec2:DescribeImages",
                        "ec2:DescribeAvailabilityZones",
                        # Tags
                        "ec2:CreateTags",
                        "ec2:DeleteTags",
                        "ec2:DescribeTags",
                        # IPv6
                        "ec2:AssociateVpcCidrBlock",
                        "ec2:DisassociateVpcCidrBlock",
                        "ec2:AssociateSubnetCidrBlock",
                        "ec2:DisassociateSubnetCidrBlock",
                        "ec2:ModifySubnetAttribute",
                        # Network interfaces (spot instances)
                        "ec2:DescribeNetworkInterfaces",
                        # Account attributes (needed by Pulumi provider)
                        "ec2:DescribeAccountAttributes",
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

# =============================================================================
# Public ECR Repository
# =============================================================================

# ECR Public repositories can only be created in us-east-1.
aws_us_east_1 = aws.Provider(
    f"{prefix}-us-east-1",
    region="us-east-1",
)

ecr_repo = aws.ecrpublic.Repository(
    f"{prefix}-ecr",
    repository_name="openclaw",
    catalog_data={
        "architectures": ["ARM"],
        "operating_systems": ["Linux"],
        "description": "OpenClaw Docker image",
    },
    tags={"Name": f"{prefix}-ecr"},
    opts=pulumi.ResourceOptions(provider=aws_us_east_1),
)

# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

pulumi.export("github_actions_role_arn", github_actions_role.arn)
pulumi.export("oidc_provider_arn", oidc_provider_arn)
pulumi.export("ecr_repository_uri", ecr_repo.repository_uri)

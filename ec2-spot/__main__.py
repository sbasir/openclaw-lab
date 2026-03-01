"""EC2 Spot infrastructure for OpenClaw Lab.

This stack manages ephemeral compute resources:
  - VPC with multi-AZ public subnets (IPv4 + IPv6)
  - Internet Gateway and Route Tables
  - Security groups (SSM-only access, no inbound ports)
  - EC2 Spot instance with persistent request
  - Elastic IP for stable public addressing
  - Root EBS volume sized via stack configuration
  - IAM instance profile with SSM, ECR, CloudWatch, and Parameter Store access

The stack references the platform stack to obtain the ECR repository URL.
"""

import json

import pulumi
import pulumi_aws as aws
from network_helpers import (
    ipv4_subnets_cidrs,
    canonicalize_ipv4_cidr,
    ipv6_subnets_cidrs,
)
from dashboard_builder import create_minimal_dashboard_body

from user_data import build_user_data

prefix = "openclaw-lab"
config = pulumi.Config()

# set via: pulumi config set ami ami-0123456789abcdef --stack dev
ami_override = config.get("ami")

# set via: pulumi config set instance_type t4g.small --stack dev
ec2_instance_type = config.get("instance_type") or "t4g.small"  # 2 VCPUs, 2 GB RAM
# set via: pulumi config set cidr_block 10.0.0.0/16 --stack dev
cidr_block = canonicalize_ipv4_cidr(config.get("cidr_block") or "10.0.0.0/16")
# set via: pulumi config set root_volume_size_gib 15 --stack dev
root_volume_size_gib = int(config.get("root_volume_size_gib") or "15")
# set via: pulumi config set availability_zone me-central-1a --stack dev
availability_zone = config.require("availability_zone")

if not aws.config.region:
    raise ValueError("AWS region must be configured (e.g. 'me-central-1').")

# AWS region is determined by provider configuration (environment or stack config).
aws_region = aws.config.region

# Reference the platform stack to get ECR repository URL.
# Assumes the platform stack has the same stack name (e.g., 'dev').
# The ECR URL is used in the cloud-init user data for Docker image pulls.
platform_stack = pulumi.StackReference(
    f"{pulumi.get_organization()}/openclaw-platform/{pulumi.get_stack()}"
)
ecr_repository_url = platform_stack.require_output("ecr_repository_url")
s3_backup_bucket_name = platform_stack.require_output("s3_backup_bucket_name")
s3_scripts_bucket_name = platform_stack.require_output("s3_scripts_bucket_name")


# -----------------------------------------------------------------------------
# IAM Role and Instance Profile for SSM and Parameter Store access
# -----------------------------------------------------------------------------


# IAM Role for the EC2 instance
instance_assume_role_policy = aws.iam.get_policy_document(
    statements=[
        {
            "actions": ["sts:AssumeRole"],
            "principals": [
                {
                    "type": "Service",
                    "identifiers": ["ec2.amazonaws.com"],
                }
            ],
        }
    ]
)

ec2_role = aws.iam.Role(
    f"{prefix}-role",
    name=f"{prefix}-role",
    assume_role_policy=instance_assume_role_policy.json,
    description=("IAM role for EC2 instance"),
    tags={"Name": f"{prefix}-role"},
)

# Attach AWS managed policy for SSM Session Manager
aws.iam.RolePolicyAttachment(
    f"{prefix}-ssm-policy",
    role=ec2_role.name,
    policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
)

# Attach AWS managed policy for CloudWatch agent server operations.
aws.iam.RolePolicyAttachment(
    f"{prefix}-cloudwatch-agent-policy",
    role=ec2_role.name,
    policy_arn="arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy",
)

# Allow EC2 instance to pull from ECR (for private repository access)
aws.iam.RolePolicyAttachment(
    f"{prefix}-ecr-policy",
    role=ec2_role.name,
    policy_arn="arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly",
)

# Custom policy for SSM Parameter Store access (read-only for OpenClaw config).
aws.iam.RolePolicy(
    f"{prefix}-parameter-store-policy",
    role=ec2_role.name,
    policy=aws.iam.get_policy_document(
        statements=[
            {
                "actions": [
                    "ssm:GetParameter",
                    "ssm:GetParameters",
                    "ssm:GetParametersByPath",
                ],
                "resources": [
                    f"arn:aws:ssm:{aws_region}:{aws.get_caller_identity().account_id}:parameter/openclaw-lab/*"
                ],
            }
        ],
    ).json,
)

aws.iam.RolePolicy(
    f"{prefix}-s3-backup-policy",
    role=ec2_role.name,
    policy=s3_backup_bucket_name.apply(
        lambda bucket: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "OpenClawS3Backup",
                        "Effect": "Allow",
                        "Action": [
                            "s3:ListBucket",
                            "s3:GetObject",
                            "s3:PutObject",
                            "s3:DeleteObject",
                            "s3:AbortMultipartUpload",
                            "s3:ListBucketMultipartUploads",
                            "s3:ListMultipartUploadParts",
                        ],
                        "Resource": [
                            f"arn:aws:s3:::{bucket}",
                            f"arn:aws:s3:::{bucket}/*",
                        ],
                    }
                ],
            }
        )
    ),
)

aws.iam.RolePolicy(
    f"{prefix}-s3-scripts-policy",
    role=ec2_role.name,
    policy=s3_scripts_bucket_name.apply(
        lambda bucket: json.dumps(
            {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "OpenClawS3Scripts",
                        "Effect": "Allow",
                        "Action": [
                            "s3:GetObject",
                        ],
                        "Resource": [
                            f"arn:aws:s3:::{bucket}/*",
                        ],
                    }
                ],
            }
        )
    ),
)

# Instance Profile to attach the role to EC2
ec2_instance_profile = aws.iam.InstanceProfile(
    f"{prefix}-instance-profile",
    role=ec2_role.name,
    tags={"Name": f"{prefix}-instance-profile"},
)

# -----------------------------------------------------------------------------
# Networking: VPC, Subnets, Internet Gateway, Route Table, Security Group
# -----------------------------------------------------------------------------

vpc = aws.ec2.Vpc(
    f"{prefix}-vpc",
    cidr_block=cidr_block,
    assign_generated_ipv6_cidr_block=True,
    tags={"Name": f"{prefix}-vpc"},
)

igw = aws.ec2.InternetGateway(
    f"{prefix}-igw",
    vpc_id=vpc.id,
    tags={"Name": f"{prefix}-igw"},
)

rt = aws.ec2.RouteTable(
    f"{prefix}-rt",
    vpc_id=vpc.id,
    tags={"Name": f"{prefix}-rt"},
)

ipv4_route = aws.ec2.Route(
    f"{prefix}-ipv4-route",
    route_table_id=rt.id,
    destination_cidr_block="0.0.0.0/0",
    gateway_id=igw.id,
)
ipv6_route = aws.ec2.Route(
    f"{prefix}-ipv6-route",
    route_table_id=rt.id,
    destination_ipv6_cidr_block="::/0",
    gateway_id=igw.id,
)

# Validate the selected availability zone
azs = aws.get_availability_zones(region=aws_region).names
if availability_zone not in azs:
    raise ValueError(
        f"availability_zone '{availability_zone}' is not in available AZs: {azs}"
    )

pulumi.export("selected_az", availability_zone)

# Create a single subnet in the selected AZ (no need for subnets in unused AZs)
ipv4_cidrs = ipv4_subnets_cidrs(cidr_block, 1)
ipv6_cidrs = ipv6_subnets_cidrs(vpc.ipv6_cidr_block, 1)

subnet = aws.ec2.Subnet(
    f"{prefix}-public-subnet",
    vpc_id=vpc.id,
    cidr_block=ipv4_cidrs[0],
    ipv6_cidr_block=ipv6_cidrs[0],
    assign_ipv6_address_on_creation=True,
    availability_zone=availability_zone,
    tags={"Name": f"{prefix}-public-subnet-{availability_zone}"},
)

aws.ec2.RouteTableAssociation(
    f"{prefix}-public-subnet-association",
    subnet_id=subnet.id,
    route_table_id=rt.id,
)

# Security group for EC2 instance (no inbound rules; access via SSM only).
ec2_sg = aws.ec2.SecurityGroup(
    f"{prefix}-sg",
    description="Security group for Spot Instance",
    vpc_id=vpc.id,
    tags={"Name": f"{prefix}-sg"},
)

# Egress: Allow all outbound traffic (required for SSM, package updates, etc.)
aws.ec2.SecurityGroupRule(
    f"{prefix}-egress-all",
    type="egress",
    from_port=0,
    to_port=0,
    protocol="-1",
    cidr_blocks=["0.0.0.0/0"],
    security_group_id=ec2_sg.id,
    description="Allow all outbound traffic",
)

# Egress: Allow all outbound traffic (IPv6)
aws.ec2.SecurityGroupRule(
    f"{prefix}-egress-all-ipv6",
    type="egress",
    from_port=0,
    to_port=0,
    protocol="-1",
    ipv6_cidr_blocks=["::/0"],
    security_group_id=ec2_sg.id,
    description="Allow all outbound traffic (IPv6)",
)

# -----------------------------------------------------------------------------
# EC2 Spot Instance for OpenClaw Lab Server
# -----------------------------------------------------------------------------

if ami_override:
    ami = aws.ec2.get_ami(
        filters=[{"name": "image-id", "values": [ami_override]}],
    )
else:
    ami = aws.ec2.get_ami(
        most_recent=True,
        owners=["amazon"],
        filters=[
            {"name": "name", "values": ["al2023-ami-2023*-arm64"]},
            {"name": "virtualization-type", "values": ["hvm"]},
            {"name": "root-device-type", "values": ["ebs"]},
            {"name": "architecture", "values": ["arm64"]},
        ],
    )


# Create the Spot Instance Request with persistent type.
# Instance will be restarted (not terminated) if interrupted.
spot = aws.ec2.SpotInstanceRequest(
    f"{prefix}-spot",
    ami=ami.id,
    instance_type=ec2_instance_type,  # ARM-based instance (t4g.small default)
    iam_instance_profile=ec2_instance_profile.name,
    vpc_security_group_ids=[ec2_sg.id],
    subnet_id=subnet.id,
    associate_public_ip_address=True,
    ipv6_address_count=1,
    user_data=pulumi.Output.all(
        ecr_repository_url, s3_backup_bucket_name, s3_scripts_bucket_name
    ).apply(
        lambda args: build_user_data(
            aws_region=aws_region,
            ecr_repository_url=args[0],
            s3_backup_bucket_name=args[1],
            s3_scripts_bucket_name=args[2],
        )
    ),
    # Spot instance configuration: persistent request with stop behavior.
    spot_type="persistent",  # Keeps requesting if interrupted
    instance_interruption_behavior="stop",  # Stop instead of terminate on interruption
    wait_for_fulfillment=True,  # Wait for the spot request to be fulfilled
    # Use standard credit mode to avoid burst charges
    credit_specification={"cpu_credits": "standard"},
    # Metadata options for IMDSv2 (more secure)
    metadata_options={
        "http_endpoint": "enabled",
        "http_tokens": "required",  # Require IMDSv2
        "http_put_response_hop_limit": 1,
    },
    # Root volume configuration
    root_block_device={
        "volume_type": "gp3",
        "volume_size": root_volume_size_gib,
        "delete_on_termination": True,
        "encrypted": True,
    },
    tags={
        "Name": f"{prefix}-spot",
        "Purpose": "OpenClaw Lab Server",
    },
)


aws.ec2.Tag(
    f"{prefix}-spot-name-tag",
    resource_id=spot.spot_instance_id,
    key="Name",
    value=f"{prefix}-spot-instance",
    opts=pulumi.ResourceOptions(depends_on=[spot]),
)

# Allocate an Elastic IP so the public IP remains stable across reboots.
ec2_eip = aws.ec2.Eip(
    f"{prefix}-eip",
    domain="vpc",
    instance=spot.spot_instance_id,
    opts=pulumi.ResourceOptions(depends_on=[igw]),
    tags={"Name": f"{prefix}-eip"},
)

# Associate the EIP with the Spot Instance when the instance ID is ready.
aws.ec2.EipAssociation(
    f"{prefix}-eip-assoc",
    instance_id=spot.spot_instance_id,
    allocation_id=ec2_eip.allocation_id,
)


# -----------------------------------------------------------------------------
# CloudWatch Dashboard for Observability
# -----------------------------------------------------------------------------


def create_dashboard_body(instance_id: str) -> str:
    """Create minimal dashboard JSON via extracted module."""
    return create_minimal_dashboard_body(
        instance_id=instance_id,
        aws_region=aws_region,
        stack_name=pulumi.get_stack(),
    )


# Create CloudWatch Dashboard for comprehensive observability
# Phase 1: single-widget dashboard to validate schema end-to-end.
dashboard = aws.cloudwatch.Dashboard(
    f"{prefix}-dashboard",
    dashboard_name=f"{prefix}-observability",
    dashboard_body=spot.spot_instance_id.apply(create_dashboard_body),
)

# Export useful information
pulumi.export("ami_id", ami.id)
pulumi.export("ami_name", ami.name)
pulumi.export("instance_id", spot.spot_instance_id)
pulumi.export("public_ip", ec2_eip.public_ip)
pulumi.export("spot_request_id", spot.id)
pulumi.export("iam_role_arn", ec2_role.arn)

# SSM Session Manager connect command
pulumi.export(
    "ssm_connect_command",
    spot.spot_instance_id.apply(
        lambda id: f"aws ssm start-session --target {id} --region {aws_region}"
    ),
)

# CloudWatch Dashboard URL
pulumi.export(
    "dashboard_url",
    pulumi.Output.concat(
        f"https://console.aws.amazon.com/cloudwatch/home?region={aws_region}#dashboards:name=",
        dashboard.dashboard_name,
    ),
)

# Expose the configured root volume size for bookkeeping
pulumi.export("root_volume_size_gib", root_volume_size_gib)

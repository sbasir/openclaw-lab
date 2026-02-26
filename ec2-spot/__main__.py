"""EC2 Spot infrastructure for OpenClaw Lab.

This stack manages ephemeral compute resources:
  - VPC with multi-AZ public subnets (IPv4 + IPv6)
  - Internet Gateway and Route Tables
  - Security groups (SSM-only access, no inbound ports)
  - EC2 Spot instance with persistent request
  - Elastic IP for stable public addressing
  - EBS data volume with DLM-managed snapshots
  - IAM instance profile with SSM, ECR, CloudWatch, and Parameter Store access

The stack references the platform stack to obtain the ECR repository URL.
"""

import pulumi
import pulumi_aws as aws
from network_helpers import (
    ipv4_subnets_cidrs,
    canonicalize_ipv4_cidr,
    ipv6_subnets_cidrs,
)

from user_data import build_user_data

prefix = "openclaw-lab"
config = pulumi.Config()

# set via: pulumi config set ami ami-0123456789abcdef --stack dev
ami_override = config.get("ami")

# set via: pulumi config set instance_type t4g.small --stack dev
ec2_instance_type = config.get("instance_type") or "t4g.small"  # 2 VCPUs, 2 GB RAM
# set via: pulumi config set cidr_block 10.0.0.0/16 --stack dev
cidr_block = canonicalize_ipv4_cidr(config.get("cidr_block") or "10.0.0.0/16")
# set via: pulumi config set data_volume_size_gib 20 --stack dev
data_volume_size_gib = int(config.get("data_volume_size_gib") or "20")
# set via: pulumi config set data_device_name /dev/sdf --stack dev
data_device_name = config.get("data_device_name") or "/dev/sdf"
# set via: pulumi config set data_volume_snapshot_id snap-0123456789abcdef0 --stack dev
data_volume_snapshot_id = config.get("data_volume_snapshot_id")
# set via: pulumi config set availability_zone me-central-1a --stack dev
availability_zone = config.require("availability_zone")
# set via: pulumi config set snapshot_schedule_interval_hours 24 --stack dev
snapshot_schedule_interval_hours = int(
    config.get("snapshot_schedule_interval_hours") or "24"
)
# set via: pulumi config set snapshot_schedule_time 03:00 --stack dev
snapshot_schedule_time = config.get("snapshot_schedule_time")
# set via: pulumi config set snapshot_retention_days 30 --stack dev
snapshot_retention_days = int(config.get("snapshot_retention_days") or "30")

if snapshot_retention_days < 1:
    raise ValueError("snapshot_retention_days must be >= 1")

if snapshot_schedule_interval_hours < 1:
    raise ValueError("snapshot_schedule_interval_hours must be >= 1")

if not snapshot_schedule_time and snapshot_schedule_interval_hours == 24:
    snapshot_schedule_time = "03:00"

if snapshot_schedule_time and snapshot_schedule_interval_hours != 24:
    raise ValueError(
        "snapshot_schedule_time can only be set when snapshot_schedule_interval_hours is 24"
    )

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

# Instance Profile to attach the role to EC2
ec2_instance_profile = aws.iam.InstanceProfile(
    f"{prefix}-instance-profile",
    role=ec2_role.name,
    tags={"Name": f"{prefix}-instance-profile"},
)

# IAM role for Data Lifecycle Manager to create and manage EBS snapshots.
dlm_assume_role_policy = aws.iam.get_policy_document(
    statements=[
        {
            "actions": ["sts:AssumeRole"],
            "principals": [
                {
                    "type": "Service",
                    "identifiers": ["dlm.amazonaws.com"],
                }
            ],
        }
    ]
)

dlm_role = aws.iam.Role(
    f"{prefix}-dlm-role",
    name=f"{prefix}-dlm-role",
    assume_role_policy=dlm_assume_role_policy.json,
    description="IAM role for AWS Data Lifecycle Manager snapshots",
    tags={"Name": f"{prefix}-dlm-role"},
)

aws.iam.RolePolicyAttachment(
    f"{prefix}-dlm-role-policy",
    role=dlm_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AWSDataLifecycleManagerServiceRole",
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


def create_public_subnet(
    az: str, subnet_ipv4_cidr: str, subnet_ipv6_cidr: pulumi.Input[str]
) -> aws.ec2.Subnet:
    return aws.ec2.Subnet(
        f"{prefix}-public-subnet-{az}",
        vpc_id=vpc.id,
        cidr_block=subnet_ipv4_cidr,
        ipv6_cidr_block=subnet_ipv6_cidr,
        assign_ipv6_address_on_creation=True,
        availability_zone=az,
        tags={"Name": f"{prefix}-public-subnet-{az}"},
    )


azs = aws.get_availability_zones(region=aws_region).names

if availability_zone not in azs:
    raise ValueError(
        f"availability_zone '{availability_zone}' is not in available AZs: {azs}"
    )

selected_az = availability_zone

if data_volume_snapshot_id:
    snapshot = aws.ebs.get_snapshot(snapshot_ids=[data_volume_snapshot_id])
    snapshot_expected_az = snapshot.tags.get("OpenClawAz") if snapshot.tags else None

    if snapshot_expected_az and selected_az != snapshot_expected_az:
        raise ValueError(
            "Configured availability_zone does not match snapshot OpenClawAz tag: "
            f"availability_zone='{selected_az}', snapshot OpenClawAz='{snapshot_expected_az}'."
        )

    if not snapshot_expected_az:
        raise ValueError(
            "Snapshot is missing required OpenClawAz tag; cannot validate AZ guardrail. "
            "Any snapshot used (whether created by this stack's DLM policy or manually) "
            "must be tagged with OpenClawAz matching the original data volume "
            "availability_zone."
        )

pulumi.export("selected_az", selected_az)

ipv4_cidrs = ipv4_subnets_cidrs(cidr_block, len(azs))
ipv6_cidrs = ipv6_subnets_cidrs(vpc.ipv6_cidr_block, len(azs))
subnets: list[aws.ec2.Subnet] = []

for az, ipv4_cidr, ipv6_cidr in zip(azs, ipv4_cidrs, ipv6_cidrs):
    subnet = create_public_subnet(az, ipv4_cidr, ipv6_cidr)
    subnets.append(subnet)
    aws.ec2.RouteTableAssociation(
        f"{prefix}-public-subnet-{az}-association",
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


subnet_in_selected_az = {az: subnet for az, subnet in zip(azs, subnets)}[selected_az]

# Create the Spot Instance Request with persistent type.
# Instance will be restarted (not terminated) if interrupted.
spot = aws.ec2.SpotInstanceRequest(
    f"{prefix}-spot",
    ami=ami.id,
    instance_type=ec2_instance_type,  # ARM-based instance (t4g.small default)
    iam_instance_profile=ec2_instance_profile.name,
    vpc_security_group_ids=[ec2_sg.id],
    subnet_id=subnet_in_selected_az.id,
    associate_public_ip_address=True,
    ipv6_address_count=1,
    user_data=ecr_repository_url.apply(
        lambda url: build_user_data(
            aws_region=aws_region,
            ecr_repository_url=url,
            openclaw_data_device_name=data_device_name,
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
        "volume_size": 8,
        "delete_on_termination": True,
        "encrypted": True,
    },
    tags={
        "Name": f"{prefix}-spot",
        "Purpose": "OpenClaw Lab Server",
    },
)

# Dedicated EBS volume for persistent OpenClaw data.
# Tagged for DLM snapshot lifecycle management.
data_volume = aws.ebs.Volume(
    f"{prefix}-data-volume",
    availability_zone=selected_az,
    size=data_volume_size_gib,
    type="gp3",
    encrypted=True,
    snapshot_id=data_volume_snapshot_id,
    tags={
        "Name": f"{prefix}-data-volume",
        "Purpose": "OpenClaw Persistent Data",
        "OpenClawData": "true",
        "OpenClawStack": pulumi.get_stack(),
        "OpenClawAz": selected_az,
    },
)

# Data Lifecycle Manager policy for automated EBS snapshots.
# Snapshots are taken on schedule and pruned based on retention policy.
aws.dlm.LifecyclePolicy(
    f"{prefix}-data-volume-snapshot-policy",
    description="OpenClaw data volume scheduled snapshots",
    execution_role_arn=dlm_role.arn,
    state="ENABLED",
    policy_details=aws.dlm.LifecyclePolicyPolicyDetailsArgs(
        resource_types=["VOLUME"],
        target_tags={
            "OpenClawData": "true",
            "OpenClawStack": pulumi.get_stack(),
        },
        schedules=[
            aws.dlm.LifecyclePolicyPolicyDetailsScheduleArgs(
                name="openclaw-data-snapshot",
                copy_tags=True,
                create_rule=aws.dlm.LifecyclePolicyPolicyDetailsScheduleCreateRuleArgs(
                    interval=snapshot_schedule_interval_hours,
                    interval_unit="HOURS",
                    times=snapshot_schedule_time,
                ),
                retain_rule=aws.dlm.LifecyclePolicyPolicyDetailsScheduleRetainRuleArgs(
                    interval=snapshot_retention_days,
                    interval_unit="DAYS",
                ),
                tags_to_add={
                    "CreatedBy": "dlm",
                    "OpenClawData": "true",
                    "OpenClawStack": pulumi.get_stack(),
                },
            )
        ],
    ),
    tags={
        "Name": f"{prefix}-data-volume-snapshot-policy",
    },
)

# Attach data volume to the Spot instance.
# delete_before_replace prevents VolumeInUse errors during replacement.
aws.ec2.VolumeAttachment(
    f"{prefix}-data-volume-attachment",
    device_name=data_device_name,
    volume_id=data_volume.id,
    instance_id=spot.spot_instance_id,
    stop_instance_before_detaching=True,
    opts=pulumi.ResourceOptions(
        depends_on=[spot, data_volume],
        delete_before_replace=True,
    ),
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
    """Create CloudWatch Dashboard JSON configuration.
    
    Provides comprehensive observability for the OpenClaw EC2 instance including:
    - EC2 instance metrics (CPU, status checks)
    - Custom CloudWatch Agent metrics (CPU, Memory, Disk, Network)
    - Disk I/O and network performance
    - SSM Agent connectivity status
    - CloudWatch Logs insights
    """
    import json
    
    return json.dumps({
        "widgets": [
            # Row 1: Title and Instance Status
            {
                "type": "text",
                "x": 0,
                "y": 0,
                "width": 24,
                "height": 1,
                "properties": {
                    "markdown": f"# OpenClaw Lab - EC2 Spot Instance Observability\n**Instance ID:** `{instance_id}` | **Region:** `{aws_region}` | **Stack:** `{pulumi.get_stack()}`"
                }
            },
            {
                "type": "metric",
                "x": 0,
                "y": 1,
                "width": 6,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/EC2", "StatusCheckFailed", {"stat": "Maximum", "label": "Status Check Failed"}],
                        [".", "StatusCheckFailed_Instance", {"stat": "Maximum", "label": "Instance Check Failed"}],
                        [".", "StatusCheckFailed_System", {"stat": "Maximum", "label": "System Check Failed"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "EC2 Status Checks",
                    "period": 300,
                    "yAxis": {"left": {"min": 0, "max": 1}},
                    "annotations": {
                        "horizontal": [{
                            "value": 0,
                            "label": "Healthy",
                            "fill": "below"
                        }]
                    }
                }
            },
            {
                "type": "metric",
                "x": 6,
                "y": 1,
                "width": 6,
                "height": 3,
                "properties": {
                    "metrics": [
                        ["OpenClawLab/EC2", "CPU_USER", {"stat": "Average", "label": "CPU User"}],
                        [".", "CPU_SYSTEM", {"stat": "Average", "label": "CPU System"}],
                        [".", "CPU_IOWAIT", {"stat": "Average", "label": "CPU IOWait"}]
                    ],
                    "view": "singleValue",
                    "region": aws_region,
                    "title": "Current CPU Usage (%)",
                    "period": 60,
                    "setPeriodToTimeRange": False
                }
            },
            {
                "type": "metric",
                "x": 12,
                "y": 1,
                "width": 6,
                "height": 3,
                "properties": {
                    "metrics": [
                        ["OpenClawLab/EC2", "MEM_USED_PERCENT", {"stat": "Average", "label": "Memory Used"}],
                        [".", "MEM_AVAILABLE_PERCENT", {"stat": "Average", "label": "Memory Available"}]
                    ],
                    "view": "singleValue",
                    "region": aws_region,
                    "title": "Current Memory Usage (%)",
                    "period": 60,
                    "setPeriodToTimeRange": False
                }
            },
            {
                "type": "metric",
                "x": 18,
                "y": 1,
                "width": 6,
                "height": 3,
                "properties": {
                    "metrics": [
                        ["OpenClawLab/EC2", "DISK_USED_PERCENT", {"stat": "Average", "label": "Root (/)"}],
                        ["...", {"fstype": "ext4", "path": "/opt/openclaw", "stat": "Average", "label": "Data (/opt/openclaw)"}]
                    ],
                    "view": "singleValue",
                    "region": aws_region,
                    "title": "Current Disk Usage (%)",
                    "period": 60,
                    "setPeriodToTimeRange": False
                }
            },
            {
                "type": "log",
                "x": 6,
                "y": 4,
                "width": 18,
                "height": 3,
                "properties": {
                    "query": f"SOURCE '/aws/ec2/openclaw-lab/{instance_id}'\n| fields @timestamp, @message\n| filter @message like /error|Error|ERROR|fail|Fail|FAIL|warn|Warn|WARN/\n| sort @timestamp desc\n| limit 20",
                    "region": aws_region,
                    "title": "Recent Errors & Warnings (CloudWatch Logs)",
                    "stacked": False
                }
            },
            
            # Row 2: CPU Metrics
            {
                "type": "text",
                "x": 0,
                "y": 7,
                "width": 24,
                "height": 1,
                "properties": {
                    "markdown": "## CPU Performance"
                }
            },
            {
                "type": "metric",
                "x": 0,
                "y": 8,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["OpenClawLab/EC2", "CPU_USER", {"stat": "Average", "label": "User", "color": "#1f77b4"}],
                        [".", "CPU_SYSTEM", {"stat": "Average", "label": "System", "color": "#ff7f0e"}],
                        [".", "CPU_IOWAIT", {"stat": "Average", "label": "IOWait", "color": "#d62728"}],
                        [".", "CPU_IDLE", {"stat": "Average", "label": "Idle", "color": "#2ca02c"}]
                    ],
                    "view": "timeSeries",
                    "stacked": True,
                    "region": aws_region,
                    "title": "CPU Usage Breakdown (Stacked)",
                    "period": 60,
                    "yAxis": {"left": {"min": 0, "max": 100}},
                    "annotations": {
                        "horizontal": [{
                            "value": 80,
                            "label": "High CPU Threshold",
                            "fill": "above"
                        }]
                    }
                }
            },
            {
                "type": "metric",
                "x": 12,
                "y": 8,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/EC2", "CPUUtilization", {"stat": "Average", "label": "Average"}],
                        ["...", {"stat": "Maximum", "label": "Maximum"}],
                        ["...", {"stat": "Minimum", "label": "Minimum"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "EC2 CPU Utilization (Hypervisor View)",
                    "period": 300,
                    "yAxis": {"left": {"min": 0, "max": 100}},
                    "annotations": {
                        "horizontal": [{
                            "value": 80,
                            "label": "High CPU",
                            "fill": "above"
                        }]
                    }
                }
            },
            
            # Row 3: Memory Metrics
            {
                "type": "text",
                "x": 0,
                "y": 14,
                "width": 24,
                "height": 1,
                "properties": {
                    "markdown": "## Memory Performance"
                }
            },
            {
                "type": "metric",
                "x": 0,
                "y": 15,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["OpenClawLab/EC2", "MEM_USED_PERCENT", {"stat": "Average", "label": "Used %", "color": "#d62728"}],
                        [".", "MEM_AVAILABLE_PERCENT", {"stat": "Average", "label": "Available %", "color": "#2ca02c"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "Memory Usage (%)",
                    "period": 60,
                    "yAxis": {"left": {"min": 0, "max": 100}},
                    "annotations": {
                        "horizontal": [{
                            "value": 80,
                            "label": "High Memory Threshold",
                            "fill": "above"
                        }]
                    }
                }
            },
            {
                "type": "metric",
                "x": 12,
                "y": 15,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["OpenClawLab/EC2", "MEM_USED_BYTES", {"stat": "Average", "label": "Used"}],
                        [".", "MEM_AVAILABLE_BYTES", {"stat": "Average", "label": "Available"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "Memory Usage (Bytes)",
                    "period": 60,
                    "yAxis": {"left": {"min": 0}}
                }
            },
            
            # Row 4: Disk Usage
            {
                "type": "text",
                "x": 0,
                "y": 21,
                "width": 24,
                "height": 1,
                "properties": {
                    "markdown": "## Disk Usage & Performance"
                }
            },
            {
                "type": "metric",
                "x": 0,
                "y": 22,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["OpenClawLab/EC2", "DISK_USED_PERCENT", {"stat": "Average", "label": "Root (/)", "path": "/"}],
                        ["...", {"path": "/opt/openclaw", "stat": "Average", "label": "Data (/opt/openclaw)"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "Disk Space Used (%)",
                    "period": 300,
                    "yAxis": {"left": {"min": 0, "max": 100}},
                    "annotations": {
                        "horizontal": [{
                            "value": 80,
                            "label": "High Disk Usage",
                            "fill": "above"
                        }]
                    }
                }
            },
            {
                "type": "metric",
                "x": 8,
                "y": 22,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["OpenClawLab/EC2", "INODE_USED", {"stat": "Average", "label": "Inodes Used"}],
                        [".", "INODE_FREE", {"stat": "Average", "label": "Inodes Free"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "Inode Usage",
                    "period": 300,
                    "yAxis": {"left": {"min": 0}}
                }
            },
            {
                "type": "metric",
                "x": 16,
                "y": 22,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/EBS", "VolumeReadBytes", {"stat": "Sum", "label": "Read Bytes"}],
                        [".", "VolumeWriteBytes", {"stat": "Sum", "label": "Write Bytes"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "EBS Volume Throughput (Bytes)",
                    "period": 300,
                    "yAxis": {"left": {"min": 0}}
                }
            },
            
            # Row 5: Disk I/O Performance
            {
                "type": "metric",
                "x": 0,
                "y": 28,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["OpenClawLab/EC2", "DISK_READ_OPS", {"stat": "Sum", "label": "Read Ops"}],
                        [".", "DISK_WRITE_OPS", {"stat": "Sum", "label": "Write Ops"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "Disk I/O Operations",
                    "period": 60,
                    "yAxis": {"left": {"min": 0}}
                }
            },
            {
                "type": "metric",
                "x": 8,
                "y": 28,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["OpenClawLab/EC2", "DISK_READ_BYTES", {"stat": "Sum", "label": "Read"}],
                        [".", "DISK_WRITE_BYTES", {"stat": "Sum", "label": "Write"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "Disk I/O Throughput (Bytes)",
                    "period": 60,
                    "yAxis": {"left": {"min": 0}}
                }
            },
            {
                "type": "metric",
                "x": 16,
                "y": 28,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["OpenClawLab/EC2", "DISK_IO_TIME", {"stat": "Average", "label": "I/O Time"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "Disk I/O Time (ms)",
                    "period": 60,
                    "yAxis": {"left": {"min": 0}}
                }
            },
            
            # Row 6: Network Performance
            {
                "type": "text",
                "x": 0,
                "y": 34,
                "width": 24,
                "height": 1,
                "properties": {
                    "markdown": "## Network Performance"
                }
            },
            {
                "type": "metric",
                "x": 0,
                "y": 35,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["OpenClawLab/EC2", "NET_BYTES_SENT", {"stat": "Sum", "label": "Bytes Sent"}],
                        [".", "NET_BYTES_RECV", {"stat": "Sum", "label": "Bytes Received"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "Network Throughput (Bytes)",
                    "period": 60,
                    "yAxis": {"left": {"min": 0}}
                }
            },
            {
                "type": "metric",
                "x": 12,
                "y": 35,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["OpenClawLab/EC2", "NET_PACKETS_SENT", {"stat": "Sum", "label": "Packets Sent"}],
                        [".", "NET_PACKETS_RECV", {"stat": "Sum", "label": "Packets Received"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "Network Packets",
                    "period": 60,
                    "yAxis": {"left": {"min": 0}}
                }
            },
            {
                "type": "metric",
                "x": 0,
                "y": 41,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/EC2", "NetworkIn", {"stat": "Sum", "label": "Network In"}],
                        [".", "NetworkOut", {"stat": "Sum", "label": "Network Out"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "EC2 Network Traffic (Bytes, Hypervisor View)",
                    "period": 300,
                    "yAxis": {"left": {"min": 0}}
                }
            },
            {
                "type": "metric",
                "x": 12,
                "y": 41,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["OpenClawLab/EC2", "TCP_ESTABLISHED", {"stat": "Average", "label": "Established"}],
                        [".", "TCP_TIME_WAIT", {"stat": "Average", "label": "Time Wait"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "TCP Connection States",
                    "period": 60,
                    "yAxis": {"left": {"min": 0}}
                }
            },
            
            # Row 7: SSM & Systems Manager
            {
                "type": "text",
                "x": 0,
                "y": 47,
                "width": 24,
                "height": 1,
                "properties": {
                    "markdown": "## Systems Manager & Connectivity"
                }
            },
            {
                "type": "metric",
                "x": 0,
                "y": 48,
                "width": 12,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/SSM", "CommandsSucceeded", {"stat": "Sum", "label": "Commands Succeeded"}],
                        [".", "CommandsFailed", {"stat": "Sum", "label": "Commands Failed"}],
                        [".", "CommandsTimedOut", {"stat": "Sum", "label": "Commands Timed Out"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "SSM Command Execution Status",
                    "period": 300,
                    "yAxis": {"left": {"min": 0}}
                }
            },
            {
                "type": "log",
                "x": 12,
                "y": 48,
                "width": 12,
                "height": 6,
                "properties": {
                    "query": f"SOURCE '/aws/ec2/openclaw-lab/{instance_id}'\n| fields @timestamp, @message\n| filter @message like /cloud-init|cloudwatch-agent|docker|openclaw/\n| sort @timestamp desc\n| limit 50",
                    "region": aws_region,
                    "title": "Application & Service Logs",
                    "stacked": False
                }
            },
            
            # Row 8: EBS & Spot Instance Metrics
            {
                "type": "text",
                "x": 0,
                "y": 54,
                "width": 24,
                "height": 1,
                "properties": {
                    "markdown": "## EBS Volume Performance & Spot Instance"
                }
            },
            {
                "type": "metric",
                "x": 0,
                "y": 55,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/EBS", "VolumeReadOps", {"stat": "Sum", "label": "Read Ops"}],
                        [".", "VolumeWriteOps", {"stat": "Sum", "label": "Write Ops"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "EBS Volume Operations",
                    "period": 300,
                    "yAxis": {"left": {"min": 0}}
                }
            },
            {
                "type": "metric",
                "x": 8,
                "y": 55,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/EBS", "VolumeQueueLength", {"stat": "Average", "label": "Queue Length"}],
                        [".", "VolumeThroughputPercentage", {"stat": "Average", "label": "Throughput %"}],
                        [".", "VolumeConsumedReadWriteOps", {"stat": "Average", "label": "Consumed IOPS"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "EBS Volume Performance Metrics",
                    "period": 300,
                    "yAxis": {"left": {"min": 0}}
                }
            },
            {
                "type": "metric",
                "x": 16,
                "y": 55,
                "width": 8,
                "height": 6,
                "properties": {
                    "metrics": [
                        ["AWS/EBS", "VolumeIdleTime", {"stat": "Average", "label": "Idle Time"}]
                    ],
                    "view": "timeSeries",
                    "stacked": False,
                    "region": aws_region,
                    "title": "EBS Volume Idle Time (seconds)",
                    "period": 300,
                    "yAxis": {"left": {"min": 0}}
                }
            }
        ]
    })

# Create CloudWatch Dashboard for comprehensive observability
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
pulumi.export("data_volume_id", data_volume.id)
pulumi.export("data_volume_device_name", data_device_name)

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
        dashboard.dashboard_name
    ),
)

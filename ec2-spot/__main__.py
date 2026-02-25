"""An AWS Python Pulumi program"""

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
snapshot_schedule_time = config.get("snapshot_schedule_time") or "03:00"
# set via: pulumi config set snapshot_retention_days 30 --stack dev
snapshot_retention_days = int(config.get("snapshot_retention_days") or "30")

if snapshot_retention_days < 1:
    raise ValueError("snapshot_retention_days must be >= 1")

if snapshot_schedule_interval_hours < 1:
    raise ValueError("snapshot_schedule_interval_hours must be >= 1")

if not aws.config.region:
    raise ValueError("AWS region must be configured (e.g. 'me-central-1').")

# AWS region is determined by provider configuration (environment or stack config).
aws_region = aws.config.region

# Reference the platform stack to get ECR repository URI
# Assumes the platform stack has the same name as the current stack (e.g. 'dev')
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

# Custom policy for SSM Parameter Store access
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

# Security group for Ec2 instance
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

# Create the Spot Instance Request
spot = aws.ec2.SpotInstanceRequest(
    f"{prefix}-spot",
    ami=ami.id,
    instance_type=ec2_instance_type,  # Suitable ARM-based instance for OpenClaw Lab server
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
    # Spot instance configuration
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

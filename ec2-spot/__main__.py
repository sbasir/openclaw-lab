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
# AWS region is determined by the AWS provider configuration, which can be set via environment variables or Pulumi config.  If not set, it will default to "false" and raise an error.
aws_region = aws.config.region or "false"
# set via: pulumi config set instance_type t4g.small --stack dev
ec2_instance_type = config.get("instance_type") or "t4g.small"  # 2 VCPUs, 2 GB RAM
# set via: pulumi config set cidr_block 10.0.0.0/16 --stack dev
cidr_block = canonicalize_ipv4_cidr(config.get("cidr_block") or "10.0.0.0/16")

if not aws_region or aws_region == "false":
    raise ValueError("AWS region must be configured (e.g. 'me-central-1').")


def get_cheapest_az(
    instance_type: str, region: str, product_description: str = "Linux/UNIX"
) -> str:
    """
    Returns the cheapest Availability Zone for spot instances of the given instance type.
    Uses the provided region.  The function is synchronous (blocking).
    """
    # 1. Get all AZs in the region
    azs = aws.get_availability_zones(state="available", region=region).names

    # 2. For each AZ, fetch the most recent spot price (synchronously)
    prices: list[tuple[str, float]] = []
    for az in azs:
        price_data = aws.ec2.get_spot_price(
            instance_type=instance_type,
            filters=[
                {
                    "name": "product-description",
                    "values": [product_description],
                }
            ],
            region=region,
            availability_zone=az,
        )
        prices.append((az, float(price_data.spot_price)))
        pulumi.log.info(f"AZ: {az}, Spot Price: {price_data.spot_price}")

    # 3. Find the AZ with the lowest price
    cheapest_az: str = min(prices, key=lambda x: x[1])[0]
    return cheapest_az


cheapest_az = get_cheapest_az(instance_type=ec2_instance_type, region=aws_region)
pulumi.export("cheapest_az", cheapest_az)

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


subnet_in_cheapest_az = {az: subnet for az, subnet in zip(azs, subnets)}[cheapest_az]

# Create the Spot Instance Request
spot = aws.ec2.SpotInstanceRequest(
    f"{prefix}-spot",
    ami=ami.id,
    instance_type=ec2_instance_type,  # Suitable ARM-based instance for OpenClaw Lab server
    iam_instance_profile=ec2_instance_profile.name,
    vpc_security_group_ids=[ec2_sg.id],
    subnet_id=subnet_in_cheapest_az.id,
    associate_public_ip_address=True,
    ipv6_address_count=1,
    user_data=build_user_data(aws_region=aws_region),
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

# SSM Session Manager connect command
pulumi.export(
    "ssm_connect_command",
    spot.spot_instance_id.apply(
        lambda id: f"aws ssm start-session --target {id} --region {aws_region}"
    ),
)

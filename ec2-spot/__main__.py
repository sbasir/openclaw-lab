"""An AWS Python Pulumi program"""

import pulumi
import pulumi_aws as aws

prefix = "openclaw-lab"
config = pulumi.Config()

# set via: pulumi config set ami ami-0123456789abcdef --stack dev
ami_override = config.get("ami")
# AWS region is determined by the AWS provider configuration, which can be set via environment variables or Pulumi config.  If not set, it will default to "false" and raise an error.
aws_region = aws.config.region or "false"
# set via: pulumi config set instance_type t4g.small --stack dev
ec2_instance_type = config.get("instance_type") or "t4g.small"  # 2 VCPUs, 2 GB RAM

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
    prices = []
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
    cheapest_az = min(prices, key=lambda x: x[1])[0]
    return cheapest_az


cheapest_az = get_cheapest_az(instance_type=ec2_instance_type, region=aws_region)
pulumi.export("cheapest_az", cheapest_az)

"""An AWS Python Pulumi program"""

import pulumi
import pulumi_aws as aws

prefix = "openclaw-lab"
config = pulumi.Config()

# set via: pulumi config set ami ami-0123456789abcdef --stack dev
ami_override = config.get("ami")
aws_region = aws.config.region or "false"

if not aws_region or aws_region == "false":
    raise ValueError("AWS region must be configured (e.g. 'me-central-1').")


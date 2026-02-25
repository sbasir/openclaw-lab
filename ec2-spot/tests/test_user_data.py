"""Unit tests for user-data helpers."""

import pytest

from user_data import DEFAULT_COMPOSE_VERSION, build_user_data


@pytest.mark.parametrize("aws_region", ["us-east-1", "eu-west-1"])
def test_build_user_data_renders_cloud_config(aws_region: str) -> None:
    """Ensure the cloud-config includes expected files and services."""
    ecr_uri = "123456789012.dkr.ecr.us-east-1.amazonaws.com/openclaw"
    user_data = build_user_data(aws_region=aws_region, ecr_repository_url=ecr_uri)

    assert user_data.startswith("#cloud-config")
    assert "/home/ec2-user/docker-compose.yaml" in user_data
    assert "/etc/systemd/system/docker-compose.service" in user_data
    assert "/home/ec2-user/.env" in user_data
    assert "systemctl enable docker-compose.service" in user_data
    assert "systemctl start docker-compose.service" in user_data
    assert (
        "docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com"
        in user_data
    )


@pytest.mark.parametrize("aws_region", ["us-east-1", "eu-west-1", "ap-southeast-2"])
def test_build_user_data_includes_ssm_parameter_and_region(aws_region: str) -> None:
    """Ensure SSM fetch command contains parameter name and selected region."""
    user_data = build_user_data(
        aws_region=aws_region,
        ecr_repository_url="123.dkr.ecr.us-east-1.amazonaws.com/foo",
    )

    assert "--name '/openclaw-lab/dotenv'" in user_data
    assert f"--region {aws_region}" in user_data
    assert "aws ssm get-parameter" in user_data


def test_build_user_data_includes_compose_version() -> None:
    """Ensure compose download URL uses project default compose version."""
    user_data = build_user_data(
        aws_region="us-east-1",
        ecr_repository_url="123.dkr.ecr.us-east-1.amazonaws.com/foo",
    )
    assert (
        f"/releases/download/{DEFAULT_COMPOSE_VERSION}/docker-compose-linux-"
        in user_data
    )


def test_build_user_data_under_16kb_limit() -> None:
    """Ensure cloud-config stays under the 16KB user-data limit."""
    user_data = build_user_data(
        aws_region="us-east-1",
        ecr_repository_url="123.dkr.ecr.us-east-1.amazonaws.com/foo",
    )

    assert len(user_data) < 16384, (
        f"User-data is {len(user_data)} bytes, exceeds 16KB limit"
    )


def test_build_user_data_requires_aws_region() -> None:
    """Ensure aws_region argument is required by the function signature."""
    with pytest.raises(TypeError):
        build_user_data()  # type: ignore[call-arg]

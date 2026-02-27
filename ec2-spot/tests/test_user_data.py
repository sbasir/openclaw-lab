"""Unit tests for user-data helpers."""

import pytest

from user_data import (
    DEFAULT_COMPOSE_VERSION,
    build_user_data,
    extract_ecr_registry_domain,
)


@pytest.mark.parametrize("aws_region", ["us-east-1", "eu-west-1"])
def test_build_user_data_renders_cloud_config(aws_region: str) -> None:
    """Ensure the cloud-config includes expected files and services."""
    ecr_uri = "123456789012.dkr.ecr.us-east-1.amazonaws.com/openclaw"
    user_data = build_user_data(
        aws_region=aws_region,
        ecr_repository_url=ecr_uri,
        s3_backup_bucket_name="openclaw-backup-test",
        s3_scripts_bucket_name="openclaw-scripts-test",
    )

    assert user_data.startswith("#cloud-config")
    assert "s3://openclaw-scripts-test/docker-compose.yaml" in user_data
    assert "/etc/systemd/system/openclaw.service" in user_data
    assert "/run/openclaw/.env" in user_data
    assert "systemctl enable openclaw.service" in user_data
    assert "systemctl start openclaw.service" in user_data
    assert "aws ecr get-login-password --region" in user_data
    assert (
        "docker login --username AWS --password-stdin 123456789012.dkr.ecr.us-east-1.amazonaws.com"
        in user_data
    )
    assert "openclaw-s3-backup.timer" in user_data
    assert "openclaw-s3-restore.service" in user_data


@pytest.mark.parametrize("aws_region", ["us-east-1", "eu-west-1", "ap-southeast-2"])
def test_build_user_data_includes_ssm_parameter_and_region(aws_region: str) -> None:
    """Ensure service pre-start SSM fetch contains parameter name and region."""
    user_data = build_user_data(
        aws_region=aws_region,
        ecr_repository_url="123.dkr.ecr.us-east-1.amazonaws.com/foo",
        s3_backup_bucket_name="openclaw-backup-test",
        s3_scripts_bucket_name="openclaw-scripts-test",
    )

    assert "--name '/openclaw-lab/dotenv'" in user_data
    assert f"--region {aws_region}" in user_data
    assert "aws ssm get-parameter" in user_data


def test_build_user_data_includes_compose_version() -> None:
    """Ensure compose download URL uses project default compose version."""
    user_data = build_user_data(
        aws_region="us-east-1",
        ecr_repository_url="123.dkr.ecr.us-east-1.amazonaws.com/foo",
        s3_backup_bucket_name="openclaw-backup-test",
        s3_scripts_bucket_name="openclaw-scripts-test",
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
        s3_backup_bucket_name="openclaw-backup-test",
        s3_scripts_bucket_name="openclaw-scripts-test",
    )

    assert len(user_data) < 16384, (
        f"User-data is {len(user_data)} bytes, exceeds 16KB limit"
    )


def test_build_user_data_requires_aws_region() -> None:
    """Ensure aws_region argument is required by the function signature."""
    with pytest.raises(TypeError):
        build_user_data()  # type: ignore[call-arg]


def test_build_user_data_requires_backup_bucket() -> None:
    with pytest.raises(ValueError, match="s3_backup_bucket_name"):
        build_user_data(
            aws_region="us-east-1",
            ecr_repository_url="123.dkr.ecr.us-east-1.amazonaws.com/foo",
        )


def test_build_user_data_requires_scripts_bucket() -> None:
    with pytest.raises(ValueError, match="s3_scripts_bucket_name"):
        build_user_data(
            aws_region="us-east-1",
            ecr_repository_url="123.dkr.ecr.us-east-1.amazonaws.com/foo",
            s3_backup_bucket_name="openclaw-backup-test",
        )


def test_build_user_data_includes_data_device_name() -> None:
    user_data = build_user_data(
        aws_region="us-east-1",
        ecr_repository_url="123.dkr.ecr.us-east-1.amazonaws.com/foo",
        openclaw_data_device_name="/dev/sdg",
        s3_backup_bucket_name="openclaw-backup-test",
        s3_scripts_bucket_name="openclaw-scripts-test",
    )

    assert 'OPENCLAW_DATA_DEVICE="/dev/sdg"' in user_data
    assert "ROOT_SOURCE=$(findmnt -n -o SOURCE /)" in user_data
    assert (
        'ROOT_PARENT=$(lsblk -no PKNAME "$ROOT_SOURCE" 2>/dev/null || true)'
        in user_data
    )
    assert 'if [ -b "$OPENCLAW_DATA_DEVICE" ]; then' in user_data
    assert "LABEL_DEVICE=$(blkid -L OPENCLAW_DATA 2>/dev/null || true)" in user_data
    assert 'DATA_DEVICE="$OPENCLAW_DATA_DEVICE"' in user_data
    assert 'mountpoint -q "$OPENCLAW_HOME" || mount "$OPENCLAW_HOME"' in user_data


def test_extract_ecr_registry_domain_returns_registry_part() -> None:
    assert (
        extract_ecr_registry_domain(
            "123456789012.dkr.ecr.us-east-1.amazonaws.com/openclaw"
        )
        == "123456789012.dkr.ecr.us-east-1.amazonaws.com"
    )


@pytest.mark.parametrize(
    "ecr_repository_url",
    [
        "",
        "   ",
        "123456789012.dkr.ecr.us-east-1.amazonaws.com",
        "/openclaw",
        "123456789012.dkr.ecr.us-east-1.amazonaws.com/",
    ],
)
def test_extract_ecr_registry_domain_raises_for_invalid_format(
    ecr_repository_url: str,
) -> None:
    with pytest.raises(ValueError, match="<registry>/<repository>"):
        extract_ecr_registry_domain(ecr_repository_url)

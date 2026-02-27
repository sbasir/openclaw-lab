"""User-data cloud-init script builder for EC2 instance."""

from template_helpers import render_template

DEFAULT_COMPOSE_VERSION = "v5.0.2"
DEFAULT_OPENCLAW_DATA_DEVICE_NAME = "/dev/sdf"


def extract_ecr_registry_domain(ecr_repository_url: str) -> str:
    """Extract ECR registry domain from a repository URL.

    Example:
      123456789012.dkr.ecr.us-east-1.amazonaws.com/openclaw
      -> 123456789012.dkr.ecr.us-east-1.amazonaws.com
    """
    repository_url = ecr_repository_url.strip()
    if not repository_url or "/" not in repository_url:
        raise ValueError(
            "ecr_repository_url must be in '<registry>/<repository>' format"
        )

    registry_domain, repository_name = repository_url.split("/", 1)
    if not registry_domain or not repository_name:
        raise ValueError(
            "ecr_repository_url must be in '<registry>/<repository>' format"
        )
    return registry_domain


def build_user_data(
    aws_region: str,
    ecr_repository_url: str,
    openclaw_data_device_name: str = DEFAULT_OPENCLAW_DATA_DEVICE_NAME,
    s3_backup_bucket_name: str | None = None,
    s3_scripts_bucket_name: str | None = None,
) -> str:
    """Return the cloud-init script used to bootstrap the EC2 instance.

    This function builds the complete cloud-init YAML configuration by:
    1. Extracting the ECR registry domain from the repository URL
    2. Rendering the systemd service file with AWS region and ECR credentials
    3. Loading static templates (Docker Compose, CloudWatch config, helper scripts)
    4. Rendering the main cloud-config.yaml.j2 template with all context

    Parameters
    ----------
    aws_region : str
        AWS region for SSM Parameter Store access and ECR authentication.
    ecr_repository_url : str
        Full ECR repository URL (e.g., '123456789012.dkr.ecr.us-east-1.amazonaws.com/openclaw').
    openclaw_data_device_name : str, optional
        Device name for the persistent data volume (default: '/dev/sdf').
    s3_backup_bucket_name : str
        S3 bucket name for OpenClaw backup/restore sync.
    s3_scripts_bucket_name : str
        S3 bucket name containing bootstrap scripts (to keep cloud-init under 16KB).

    Returns
    -------
    str
        Complete cloud-init YAML configuration as a string.
    """

    registry_domain = extract_ecr_registry_domain(ecr_repository_url)

    service_context = {
        "aws_region": aws_region,
        "ecr_registry_domain": registry_domain,
    }

    if not s3_backup_bucket_name:
        raise ValueError("s3_backup_bucket_name is required for backup/restore")

    if not s3_scripts_bucket_name:
        raise ValueError("s3_scripts_bucket_name is required for bootstrap scripts")

    context = {
        "compose_version": DEFAULT_COMPOSE_VERSION,
        "openclaw_service": render_template("openclaw-service.conf", service_context),
        "aws_region": aws_region,
        "ecr_registry_domain": registry_domain,
        "openclaw_data_device_name": openclaw_data_device_name,
        "s3_backup_bucket_name": s3_backup_bucket_name,
        "s3_scripts_bucket_name": s3_scripts_bucket_name,
    }
    return render_template("cloud-config.yaml.j2", context)

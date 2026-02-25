"""User-data script builder EC2 instance."""

from template_helpers import load_template_source, render_template

DEFAULT_COMPOSE_VERSION = "v5.0.2"


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


def build_user_data(aws_region: str, ecr_repository_url: str) -> str:
    """Return the cloud-init script used to bootstrap the instance.

    Parameters
    ----------
    aws_region: AWS region for SSM parameter store access.
    ecr_repository_uri: URI of the ECR repository (e.g. 123.dkr.ecr.re.amazonaws.com/repo)
    """

    registry_domain = extract_ecr_registry_domain(ecr_repository_url)

    context = {
        "compose_version": DEFAULT_COMPOSE_VERSION,
        "cloudwatch_agent_config": load_template_source("cloudwatch-agent-config.json"),
        "docker_compose_config": load_template_source("docker-compose.yaml"),
        "docker_compose_service": load_template_source("docker-service.conf"),
        "aws_region": aws_region,
        "ecr_registry_domain": registry_domain,
    }
    return render_template("cloud-config.yaml.j2", context)

"""User-data script builder EC2 instance."""

from template_helpers import load_template_source, render_template

DEFAULT_COMPOSE_VERSION = "v5.0.2"


def build_user_data(aws_region: str) -> str:
    """Return the cloud-init script used to bootstrap the instance.

    Parameters
    ----------
    aws_region: AWS region for SSM parameter store access.
    """

    context = {
        "compose_version": DEFAULT_COMPOSE_VERSION,
        "cloudwatch_agent_config": load_template_source("cloudwatch-agent-config.json"),
        "docker_compose_config": load_template_source("docker-compose.yaml"),
        "docker_compose_service": load_template_source("docker-service.conf"),
        "aws_region": aws_region,
    }
    return render_template("cloud-config.yaml.j2", context)

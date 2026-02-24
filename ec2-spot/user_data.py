"""User-data script builder EC2 instance."""

from template_helpers import load_template_source, render_template

DEFAULT_COMPOSE_VERSION = "v5.0.2"


def build_user_data(aws_region: str, ecr_repository_uri: str) -> str:
    """Return the cloud-init script used to bootstrap the instance.

    Parameters
    ----------
    aws_region: AWS region for SSM parameter store access.
    ecr_repository_uri: URI of the ECR repository (e.g. 123.dkr.ecr.re.amazonaws.com/repo)
    """

    # Extract registry domain from repository URI
    # URI format: <account_id>.dkr.ecr.<region>.amazonaws.com/<repo_name>
    registry_domain = ecr_repository_uri.split("/")[0]

    context = {
        "compose_version": DEFAULT_COMPOSE_VERSION,
        "cloudwatch_agent_config": load_template_source("cloudwatch-agent-config.json"),
        "docker_compose_config": load_template_source("docker-compose.yaml"),
        "docker_compose_service": load_template_source("docker-service.conf"),
        "aws_region": aws_region,
        "ecr_registry_domain": registry_domain,
    }
    return render_template("cloud-config.yaml.j2", context)

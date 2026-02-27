"""Unit tests for template helper utilities."""

import jinja2
import pytest

from template_helpers import load_template_source, render_template


def test_render_template_renders_cloud_config_with_context_values() -> None:
    """Render cloud-config template and verify key substitutions are present."""
    context = {
        "compose_version": "v9.9.9",
        "openclaw_service": "[Unit]\nDescription=Demo Service",
        "aws_region": "ap-southeast-2",
        "ecr_registry_domain": "123.dkr.ecr.ap-southeast-2.amazonaws.com",
        "openclaw_data_device_name": "/dev/sdf",
        "s3_backup_bucket_name": "openclaw-backup-test",
        "s3_scripts_bucket_name": "openclaw-scripts-test",
    }

    rendered = render_template("cloud-config.yaml.j2", context)

    assert rendered.startswith("#cloud-config")
    assert "compose/releases/download/v9.9.9/docker-compose-linux-" in rendered
    assert 'OPENCLAW_DATA_DEVICE="/dev/sdf"' in rendered
    assert "s3://openclaw-scripts-test/" in rendered
    assert "Description=Demo Service" in rendered


def test_render_template_raises_for_missing_required_context_variable() -> None:
    """StrictUndefined should fail if a template variable is missing."""
    incomplete_context = {
        "compose_version": "v9.9.9",
        "aws_region": "us-east-1",
    }

    with pytest.raises(jinja2.exceptions.UndefinedError):
        render_template("cloud-config.yaml.j2", incomplete_context)


def test_render_template_raises_for_missing_template_file() -> None:
    """Rendering a missing template should raise TemplateNotFound."""
    with pytest.raises(jinja2.exceptions.TemplateNotFound, match="does-not-exist.j2"):
        render_template("does-not-exist.j2", {})


def test_load_template_source_reads_template_text() -> None:
    """Load raw template text from disk and verify expected contents."""
    source = load_template_source("openclaw-service.conf")

    assert "[Unit]" in source
    assert "ExecStart=" in source
    assert "WantedBy=multi-user.target" in source


def test_load_template_source_raises_for_missing_file() -> None:
    """Loading a missing file should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="does-not-exist.conf"):
        load_template_source("does-not-exist.conf")


@pytest.mark.parametrize("template_name", ["../pyproject.toml", "../../README.md"])
def test_load_template_source_blocks_path_traversal(template_name: str) -> None:
    """Loading outside templates directory should be rejected."""
    with pytest.raises(ValueError, match="templates directory"):
        load_template_source(template_name)

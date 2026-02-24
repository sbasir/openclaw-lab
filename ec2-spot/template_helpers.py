import os
from typing import Mapping

import jinja2


def render_template(template_name: str, context: Mapping[str, object]) -> str:
    """Render a Jinja2 template from the templates directory."""
    # Centralize template rendering to keep user-data generation consistent.
    template_dir = os.path.join(os.path.dirname(__file__), "templates")

    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_dir),
        undefined=jinja2.StrictUndefined,
    )

    template = env.get_template(template_name)
    return template.render(context)


def load_template_source(template_name: str) -> str:
    """Load a template file as plain text from the templates directory."""
    # Use raw file contents for templates that should not be Jinja-rendered.
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    template_path = os.path.join(template_dir, template_name)
    with open(template_path, "r", encoding="utf-8") as handle:
        return handle.read()

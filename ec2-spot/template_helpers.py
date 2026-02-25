import os
from functools import lru_cache
from pathlib import Path
from typing import Mapping

import jinja2


@lru_cache(maxsize=1)
def _template_environment() -> jinja2.Environment:
    template_dir = os.path.join(os.path.dirname(__file__), "templates")
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_dir),
        undefined=jinja2.StrictUndefined,
    )


def render_template(template_name: str, context: Mapping[str, object]) -> str:
    """Render a Jinja2 template from the templates directory."""
    template = _template_environment().get_template(template_name)
    return template.render(context)


def load_template_source(template_name: str) -> str:
    """Load a template file as plain text from the templates directory."""
    # Use raw file contents for templates that should not be Jinja-rendered.
    template_dir = Path(os.path.dirname(__file__)) / "templates"
    resolved_template_dir = template_dir.resolve()
    template_path = (template_dir / template_name).resolve()

    if resolved_template_dir not in template_path.parents:
        raise ValueError("template_name must resolve inside the templates directory")

    with open(template_path, "r", encoding="utf-8") as handle:
        return handle.read()

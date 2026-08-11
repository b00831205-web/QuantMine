"""Render the report context to HTML and then to PDF.

HTML is produced with Jinja2 (always available). The HTML→PDF step uses
WeasyPrint, which pulls in native libraries (Pango/cairo); its import is
deferred so the rest of the app — and HTML-only tests — do not require it.
Install it in the API environment with ``pip install weasyprint``.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATE_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html"]),
    )


def render_html(context: dict) -> str:
    """Render the report template. ``context`` must include ``L`` (labels)."""
    return _env().get_template("template.html").render(**context)


def html_to_pdf(html: str, base_url: str | None = None) -> bytes:
    """Convert rendered HTML to PDF bytes via WeasyPrint (deferred import)."""
    try:
        from weasyprint import HTML  # noqa: PLC0415 — heavy native dep, import on demand
    except ImportError as error:  # pragma: no cover - depends on runtime env
        raise RuntimeError(
            "WeasyPrint is not installed in the API environment. "
            "Install it (pip install weasyprint) to enable PDF export."
        ) from error
    return HTML(string=html, base_url=base_url or str(_TEMPLATE_DIR)).write_pdf()

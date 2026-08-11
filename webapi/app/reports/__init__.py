"""PDF factor-research report: i18n labels, charts, template, builder, data."""

from .builder import html_to_pdf, render_html
from .data import assemble_context
from .labels import resolve_lang

__all__ = ["assemble_context", "render_html", "html_to_pdf", "resolve_lang"]

"""Production entry point for the ``quantmine-web`` console script.

Serves the API and the bundled frontend from a single process, so a deployment
needs no Node runtime. Host and port come from ``QUANTMINE_WEB_HOST`` and
``QUANTMINE_WEB_PORT``. Reload is deliberately off; use ``uv run quantmine-dev`` for
development.
"""
import os
import uvicorn

def main()-> None:
    """Run the ASGI server until terminated."""
    uvicorn.run(
        'app.main:app',
        host = os.environ.get('QUANTMINE_WEB_HOST', '0.0.0.0'),
        port = int(os.environ.get('QUANTMINE_WEB_PORT', '8000'))
    )
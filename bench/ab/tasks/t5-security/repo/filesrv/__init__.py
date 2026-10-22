"""Tiny static file serving helpers used by the docs preview server."""
from .server import Response, serve_file

__all__ = ["Response", "serve_file"]

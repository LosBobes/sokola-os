"""Authentication and server-derived request context.

The client may *request* a context but never *grants* one. Identity is resolved
from an external authority (OIDC in production; a header adapter in local dev),
and the acting role/organization is resolved from the database on every request.
"""

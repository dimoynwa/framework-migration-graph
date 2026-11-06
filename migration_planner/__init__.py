"""The migration planner (spec 026): what applies to *this* service.

Separate top-level package from ``migration_oracle`` on purpose. Ingestion
builds the shared rule graph on our side; the planner runs in a service repo,
offline, and reads only the service's own files. It imports nothing from
``migration_oracle`` (no ``config``, no ``graph``, no ``mcp``, no ``pipeline``)
so it installs without Neo4j, LangChain or the model clients.

The only shared code is :mod:`migration_keys`: pure canonical-key builders, so
a rule entity and a scanner fact meet on the same key.
"""

__all__ = ["scanner"]

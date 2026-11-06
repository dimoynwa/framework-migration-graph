"""Graph entities built from research dossiers, one call per change cluster."""

from migration_oracle.pipeline.entities.run import run_dossier_entities
from migration_oracle.pipeline.entities.settings import resolve_entity_source

__all__ = ["resolve_entity_source", "run_dossier_entities"]

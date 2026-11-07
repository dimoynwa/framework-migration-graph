"""Service scanner (spec 026): a service repo's facts, read without an LLM.

The planner runs in the service repo. It reads manifests and sources with a
parser and writes one small profile; it never reads the graph, never calls a
model and never touches the network. Everything it needs to share with
ingestion lives in :mod:`migration_keys`.

Public entry points:

- :func:`scan` — discover, read, merge, write ``.migration/profile.json``
- :func:`discover` — file discovery and module roots
- :mod:`migration_planner.scanner.contract` — the extractor contract that
  specs 2–8 plug into (``ModuleEnv`` / ``PathMap`` carry what spec2 read about a
  module to the source extractors of specs 3–5)
"""

from migration_planner.scanner import builtin as _builtin  # noqa: F401  registration side effect
from migration_planner.scanner.contract import (
    SCANNER_VERSION,
    ConfigFact,
    DependencyFact,
    Diagnostic,
    FileFacts,
    FrameworkFact,
    Location,
    ManifestContext,
    ManifestFacts,
    ManifestFile,
    ModuleEnv,
    PathMap,
    SourceContext,
    Usage,
    register_manifest_reader,
    register_post_pass,
    register_source_extractor,
    reset_registry,
)
from migration_planner.scanner.discover import (
    DiscoveredFile,
    DiscoveryResult,
    Module,
    discover,
)
from migration_planner.scanner.profile import (
    Profile,
    Summary,
    default_profile_path,
    inputs_hash,
    write_profile,
)
from migration_planner.scanner.scan import NoSupportedManifest, ScanResult, scan

__all__ = [
    "SCANNER_VERSION",
    "ConfigFact",
    "DependencyFact",
    "Diagnostic",
    "DiscoveredFile",
    "DiscoveryResult",
    "FileFacts",
    "FrameworkFact",
    "Location",
    "ManifestContext",
    "ManifestFacts",
    "ManifestFile",
    "Module",
    "ModuleEnv",
    "NoSupportedManifest",
    "PathMap",
    "Profile",
    "ScanResult",
    "SourceContext",
    "Summary",
    "Usage",
    "default_profile_path",
    "discover",
    "inputs_hash",
    "register_manifest_reader",
    "register_post_pass",
    "register_source_extractor",
    "reset_registry",
    "scan",
    "write_profile",
]

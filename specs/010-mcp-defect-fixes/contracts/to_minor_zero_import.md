# `to_minor_zero` Import Contract

- **Owner:** `migration_oracle/mcp/tools/upgrade.py` — this file is the single source of truth for the `to_minor_zero` function
- **Function signature:** `def to_minor_zero(version: str) -> str` — converts `"3.5.12"` → `"3.5.0"`
- **Consumers:** `migration_oracle/mcp/tools/context.py` MUST import this function from `upgrade.py` — it must NOT redefine it
- **Prohibition:** No other file may redefine a `to_minor_zero` or `_to_minor_zero` function. If another module needs normalisation, it must import from `upgrade.py`
- **Rename note:** As part of spec 010, `_to_minor_zero` is renamed to `to_minor_zero` (leading underscore removed). All call sites within `upgrade.py` (`analyze_upgrade_path`, `build_recipe_plan`) MUST be updated to use the new name
- **Violation consequence:** Static analysis warnings on cross-module import of a private name; duplicate logic that can diverge silently

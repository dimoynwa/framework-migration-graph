"""CLI entry point for the migration oracle pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from migration_oracle import config
from migration_oracle.pipeline.entities import resolve_entity_source, run_dossier_entities
from migration_oracle.pipeline.extractors import (
    FRAMEWORK_DISPLAY_NAMES,
    get_extractor,
)
from migration_oracle.graph.queries import pipeline as pipeline_queries
from migration_oracle.pipeline._cache import resolve_cache_flags
from migration_oracle.pipeline._paths import (
    default_entities_json_path,
    default_filtered_md_path,
    default_raw_md_path,
    ensure_runs_directories,
)
from migration_oracle.pipeline.extractor import (
    refresh_flags_for_entity_input,
    run_extraction,
)
from migration_oracle.pipeline.extractors.base import HopContext, HopResult
from migration_oracle.pipeline.extractors.parsing import (
    HOP_GRANULARITIES,
    is_version_alias,
    validate_hop_granularity,
)
from migration_oracle.models.graph import is_prerelease
from migration_oracle.pipeline.filters import (
    filter_document,
    refresh_flags_for_filter_input,
    run_filter,
)
from migration_oracle.pipeline.populator import populate_graph
from migration_oracle.pipeline.research.rows import kept_rows
from migration_oracle.pipeline.research.markdown import (
    attach_raw_context,
    build_extraction_input,
    build_filter_research,
    dossiers_for_filtered_rows,
    parse_filtered_markdown,
)
from migration_oracle.pipeline.research.run import report_quota, run_research
from migration_oracle.pipeline.research.settings import load_settings as load_research_settings
from migration_oracle.pipeline.research.tools import ResearchQuotaExceeded
from migration_oracle.pipeline.triage.markdown import parse_raw_markdown
from migration_oracle.pipeline.triage.run import PreparedRange, prepare_range_documents


def _signal_note(result) -> str:
    """The signal part of the per-hop summary line (spec 027)."""
    status = getattr(result, "signal_status", "skipped")
    written = getattr(result, "signals_written", 0)
    if status == "skipped":
        return ""
    if status in ("disabled", "unavailable"):
        return f", signals {status}"
    return f", {written} classified by signals"


def _validate_model_provider() -> None:
    if not config.MODEL_PROVIDER.strip():
        raise click.ClickException(
            "MODEL_PROVIDER is not set. Set MODEL_PROVIDER to one of: "
            "bedrock, openai, anthropic, ollama, litellm, google."
        )
    if not config.MODEL_ID.strip():
        raise click.ClickException(
            f"MODEL_ID is not set (MODEL_PROVIDER={config.MODEL_PROVIDER}). The filter and "
            "entity LLM steps need an explicit model id, e.g. MODEL_ID=claude-opus-5-5."
        )


def _resolve_hop_settings(
    hop_granularity: str | None, hop_by_hop: bool | None
) -> tuple[str, bool]:
    """Resolve hop granularity/hop-by-hop mode from CLI flags with env fallback."""
    granularity = validate_hop_granularity(hop_granularity or config.HOP_GRANULARITY)
    by_hop = config.HOP_BY_HOP if hop_by_hop is None else hop_by_hop
    return granularity, by_hop


def _resolve_version_args(
    framework: str, from_version: str, to_version: str
) -> tuple[str, str]:
    """Resolve ``latest`` / ``latest-ga`` / ``X.Y.Z-SNAPSHOT`` before any path is derived."""
    if not (is_version_alias(from_version) or is_version_alias(to_version)):
        return from_version, to_version

    async def _resolve() -> tuple[str, str]:
        async with get_extractor(framework) as resolver:
            return await resolver.resolve_versions(from_version, to_version)

    try:
        resolved = asyncio.run(_resolve())
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    for requested, concrete in zip((from_version, to_version), resolved):
        if requested != concrete:
            click.echo(f"Resolved {requested} → {concrete}")
    return resolved


def _raw_is_stale(raw_path: Path, from_version: str, to_version: str) -> bool:
    """
    True when a raw file on disk does not describe exactly this one hop.

    Raw files written before hop-by-hop mode hold a whole range (for example
    ``4.0.0 → 4.1.0-RC1`` with one section per milestone) under a hop's file
    name. Reusing one feeds the wrong rows into triage and research.
    """
    if not raw_path.exists():
        return False
    try:
        parsed = parse_raw_markdown(raw_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return True
    hops = {(hop_from, hop_to) for hop_from, hop_to, _ in parsed.hops}
    return (parsed.from_version, parsed.to_version) != (from_version, to_version) or (
        hops != {(from_version, to_version)}
    )


def _materialize_raw(
    *,
    framework: str,
    display_name: str,
    from_version: str,
    to_version: str,
    hop_changes: list[tuple[str, str, list]] | None,
    existing_raw: str | None,
    range_metadata: dict | None,
    raw_path: Path,
    skip_triage: bool,
    force_triage: bool,
    retriage_from_cache: bool,
) -> PreparedRange:
    try:
        prepared = prepare_range_documents(
            framework_key=framework,
            framework_display=display_name,
            from_version=from_version,
            to_version=to_version,
            hop_changes=hop_changes,
            existing_raw=existing_raw,
            range_metadata=range_metadata,
            skip_triage=skip_triage,
            force_triage=force_triage,
            retriage_from_cache=retriage_from_cache,
        )
    except (ValueError, FileNotFoundError) as exc:
        raise click.ClickException(str(exc)) from exc
    if prepared.rewrite_raw:
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(prepared.raw_md, encoding="utf-8")
    return prepared


def _research_filter_extract(
    *,
    flags,
    filter_md: str,
    raw_md: str,
    filtered_path: Path,
    json_path: Path,
    framework_key: str,
    display_name: str,
    from_version: str,
    to_version: str,
    skip_research: bool,
    force_research: bool,
    stop_after_research: bool = False,
    entity_source: str = "filter",
    stop_after_clusters: bool = False,
    force_llm: bool = False,
):
    """Research every kept row, then either extract from dossiers or filter them.

    ``dossier`` (the default when research ran): gate on ``**Action:**``, cluster
    rows that share a pull, commit, or issue, and make one entity call per
    cluster. ``filter`` is the previous path: the filter LLM writes the migration
    document, then the entity LLM reads that document plus the research.
    ``stop_after_research`` returns before either path. ``stop_after_clusters``
    writes ``runs/clusters/`` and returns ``None``.
    """
    research_settings = load_research_settings()
    research_rows = attach_raw_context(
        kept_rows(filter_md),
        raw_md,
        shared_url_max_rows=research_settings.shared_url_max_rows,
        max_chars=research_settings.raw_context_max_chars,
    )
    try:
        dossiers = run_research(
            research_rows,
            display_name,
            (from_version, to_version),
            framework_key=framework_key,
            skip=skip_research,
            force=force_research,
        )
    except ResearchQuotaExceeded as exc:
        report_quota(exc)
        raise SystemExit(2) from exc
    if stop_after_research:
        return None
    if entity_source == "dossier" or stop_after_clusters:
        return run_dossier_entities(
            filter_md=filter_md,
            dossiers=dossiers,
            framework_key=framework_key,
            framework_display=display_name,
            hop=(from_version, to_version),
            filtered_path=filtered_path,
            json_path=json_path,
            force_llm=force_llm,
            stop_after_clusters=stop_after_clusters,
        )

    research = build_filter_research(research_rows, dossiers)
    flags = refresh_flags_for_filter_input(
        flags, filter_document(filter_md, research), filtered_path
    )
    if not flags.skip_filter_llm:
        _validate_model_provider()
    filter_result = run_filter(
        filter_md, output_path=filtered_path, flags=flags, research=research
    )

    filtered_rows = parse_filtered_markdown(filter_result.filtered_md)
    extraction_input = build_extraction_input(
        filter_result.filtered_md,
        filtered_rows,
        dossiers_for_filtered_rows(filtered_rows, research_rows, dossiers),
    )
    flags = refresh_flags_for_entity_input(
        flags,
        extraction_input.document,
        json_path,
        has_appendix=extraction_input.has_appendix,
    )
    if not flags.skip_entity_llm:
        _validate_model_provider()
    return run_extraction(
        extraction_input.document,
        framework_display=display_name,
        output_path=json_path,
        flags=flags,
        section_documents=list(extraction_input.section_documents),
        max_input_tokens=research_settings.entity_max_input_tokens,
    )


def _run_hop_by_hop(
    *,
    extractor,
    framework: str,
    display_name: str,
    from_version: str,
    to_version: str,
    granularity: str,
    extract_only: bool,
    dry_run: bool,
    skip_existing: bool,
    force: bool,
    force_extract: bool,
    force_llm: bool,
    skip_triage: bool,
    force_triage: bool,
    retriage_from_cache: bool,
    skip_research: bool,
    force_research: bool,
    stop_after_research: bool = False,
    entity_source: str = "filter",
    stop_after_clusters: bool = False,
    skip_signals: bool = False,
    force_signals: bool = False,
) -> None:
    """
    Run the whole pipeline once per version hop.

    Each hop gets its own raw/filtered/entities artifacts, its own filter and
    entity LLM calls, and its own ``Version`` node holding only the changes
    documented for that hop. Artifact caching is resolved per hop, so an
    interrupted run resumes at the first hop whose artifacts are missing.
    """

    def raw_path_for(context: HopContext) -> Path:
        return default_raw_md_path(framework, context.from_version, context.to_version)

    stale: set[HopContext] = set()

    async def _plan_and_extract() -> tuple[
        list[HopContext], dict[tuple[str, str], HopResult]
    ]:
        async with extractor:
            contexts = await extractor.plan_hops(
                from_version, to_version, granularity
            )
            stale.update(
                context
                for context in contexts
                if _raw_is_stale(
                    raw_path_for(context), context.from_version, context.to_version
                )
            )
            pending = [
                context
                for context in contexts
                if force
                or force_extract
                or not raw_path_for(context).exists()
                or context in stale
            ]
            hop_results = await extractor.extract_contexts(
                pending, per_hop_range_metadata=True
            )
            return contexts, {
                (hop.from_version, hop.to_version): hop for hop in hop_results
            }

    try:
        contexts, extracted = asyncio.run(_plan_and_extract())
    except NotImplementedError as exc:
        raise click.ClickException(str(exc)) from exc
    except (RuntimeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc

    if not contexts:
        raise click.ClickException(
            f"No {granularity}-level hops planned for "
            f"{framework} {from_version} → {to_version}."
        )

    def _hop_label(context: HopContext) -> str:
        suffix = "*" if is_prerelease(context.to_version) else ""
        return f"{context.from_version}→{context.to_version}{suffix}"

    click.echo(
        f"{display_name}: {len(contexts)} {granularity}-level hop(s) for "
        f"{from_version} → {to_version} — "
        + ", ".join(_hop_label(c) for c in contexts)
    )
    if any(is_prerelease(c.to_version) for c in contexts):
        click.echo(
            "  * milestone build — ingested normally; its Version node sorts "
            "below the GA release it precedes."
        )

    rules_written = 0
    steps_written = 0
    entities_written = 0
    hops_done = 0
    hops_skipped = 0
    hops_incomplete: list[str] = []

    for context in contexts:
        hop_from, hop_to = context.from_version, context.to_version
        raw_path = raw_path_for(context)
        filtered_path = default_filtered_md_path(framework, hop_from, hop_to)
        json_path = default_entities_json_path(framework, hop_from, hop_to)

        if skip_existing and raw_path.exists() and pipeline_queries.version_exists(
            display_name, hop_to
        ):
            click.echo(f"  · {hop_from} → {hop_to}: already populated, skipping.")
            hops_skipped += 1
            continue

        hop_is_stale = context in stale and not (force or force_extract)
        if hop_is_stale:
            click.echo(
                f"  · {hop_from} → {hop_to}: {raw_path} holds a different range "
                "(old multi-hop layout); re-extracted."
            )
        flags = resolve_cache_flags(
            raw_path=raw_path,
            filtered_path=filtered_path,
            json_path=json_path,
            force=force,
            force_extract=force_extract or hop_is_stale,
            force_llm=force_llm,
        )

        hop = extracted.get((hop_from, hop_to))
        if retriage_from_cache:
            if not raw_path.exists():
                raise click.ClickException(
                    "--retriage-from-cache requires an existing raw Markdown file "
                    f"at {raw_path}"
                )
            existing_raw = raw_path.read_text(encoding="utf-8")
            hop_changes = None
            range_metadata = None
        elif flags.skip_extraction and raw_path.exists():
            existing_raw = raw_path.read_text(encoding="utf-8")
            hop_changes = None
            range_metadata = None
        elif hop is None or not hop.changes:
            click.echo(
                f"  · {hop_from} → {hop_to}: no documented changes, "
                "LLM and graph steps skipped."
            )
            hops_skipped += 1
            continue
        else:
            existing_raw = None
            hop_changes = [(hop_from, hop_to, hop.changes)]
            range_metadata = hop.result.metadata

        prepared = _materialize_raw(
            framework=framework,
            display_name=display_name,
            from_version=hop_from,
            to_version=hop_to,
            hop_changes=hop_changes,
            existing_raw=existing_raw,
            range_metadata=range_metadata,
            raw_path=raw_path,
            skip_triage=skip_triage,
            force_triage=force_triage,
            retriage_from_cache=retriage_from_cache,
        )

        if extract_only:
            click.echo(
                f"  · {hop_from} → {hop_to}: raw Markdown "
                f"({len(prepared.raw_md.splitlines())} lines) → {raw_path}"
            )
            hops_done += 1
            continue

        extraction_result = _research_filter_extract(
            flags=flags,
            filter_md=prepared.filter_md,
            raw_md=prepared.raw_md,
            filtered_path=filtered_path,
            json_path=json_path,
            framework_key=framework,
            display_name=display_name,
            from_version=hop_from,
            to_version=hop_to,
            skip_research=skip_research,
            force_research=force_research,
            stop_after_research=stop_after_research,
            entity_source=entity_source,
            stop_after_clusters=stop_after_clusters,
            force_llm=force_llm,
        )
        if stop_after_research:
            click.echo(f"  · {hop_from} → {hop_to}: research → runs/research/")
            hops_done += 1
            continue
        if stop_after_clusters:
            click.echo(f"  · {hop_from} → {hop_to}: clusters → runs/clusters/")
            hops_done += 1
            continue
        if extraction_result.failed_clusters:
            click.echo(
                f"  · {hop_from} → {hop_to}: {extraction_result.failed_clusters} entity "
                "cluster(s) failed; artifacts written, graph not populated. Re-run to "
                "retry them from the cache."
            )
            hops_incomplete.append(f"{hop_from} → {hop_to}")
            continue
        result = populate_graph(
            batch=extraction_result.batch,
            framework_display=display_name,
            framework_key=framework,
            to_version=hop_to,
            from_version=hop_from,
            raw_md_path=str(raw_path),
            filtered_md_path=str(filtered_path),
            entities_json_path=str(json_path),
            dry_run=dry_run,
            skip_signals=skip_signals,
            force_signals=force_signals,
        )
        if result.skipped:
            click.echo(f"  · {hop_from} → {hop_to}: version node exists, not repopulated.")
            hops_skipped += 1
            continue
        rules_written += result.rules_written
        steps_written += result.steps_written
        entities_written += result.entities_written
        hops_done += 1
        click.echo(
            f"  · {hop_from} → {hop_to}: {result.rules_written} rules, "
            f"{result.steps_written} steps, {result.entities_written} entities"
            + _signal_note(result)
            + "."
        )

    if extract_only:
        click.echo(
            f"Extract-only complete — {hops_done} hop(s) written to "
            f"runs/raw/, {hops_skipped} skipped."
        )
    elif stop_after_research:
        click.echo(
            f"Stopped after research — {hops_done} hop(s) written to runs/raw/ and "
            f"runs/research/; filter LLM, entity LLM, and graph skipped "
            f"({hops_skipped} skipped)."
        )
    elif stop_after_clusters:
        click.echo(
            f"Stopped after clusters — {hops_done} hop(s) written to runs/clusters/; "
            f"entity LLM and graph skipped ({hops_skipped} skipped)."
        )
    elif dry_run:
        click.echo(
            f"Dry run complete — {hops_done} hop(s) processed; graph untouched."
        )
    else:
        click.echo(
            f"Hop-by-hop population complete: {hops_done} hop(s), "
            f"{rules_written} rules, {steps_written} steps, "
            f"{entities_written} entities ({hops_skipped} skipped)."
        )
    if hops_incomplete:
        click.echo(
            f"{len(hops_incomplete)} hop(s) had failed entity clusters and were not "
            f"populated: {', '.join(hops_incomplete)}.",
            err=True,
        )
        raise SystemExit(3)


@click.group()
def main() -> None:
    """Migration Oracle CLI."""


app = main


@click.command("export-extract-populate-framework")
@click.option("--framework", required=True, help="Registered framework extractor key.")
@click.argument("from_version")
@click.argument("to_version")
@click.option("--force", is_flag=True, help="Re-run extraction and both LLM steps.")
@click.option("--force-extract", is_flag=True, help="Re-run upstream extraction only.")
@click.option(
    "--force-llm",
    is_flag=True,
    help=(
        "Re-run the filter and entity LLM steps. In dossier mode, ignore the "
        "per-cluster entity cache."
    ),
)
@click.option("--dry-run", is_flag=True, help="Produce artifacts without graph writes.")
@click.option(
    "--skip-existing",
    is_flag=True,
    help="Skip when raw MD, filtered MD, and Version node all exist.",
)
@click.option(
    "--extract-only",
    is_flag=True,
    help="Run upstream HTTP extraction only; skip filter LLM, entity LLM, and graph.",
)
@click.option(
    "--hop-granularity",
    type=click.Choice(HOP_GRANULARITIES),
    default=None,
    help=(
        "Version step size between ingestion hops: 'minor' (one hop per minor "
        "line, default) or 'patch' (every release). "
        "Falls back to the HOP_GRANULARITY env var."
    ),
)
@click.option(
    "--hop-by-hop/--no-hop-by-hop",
    "hop_by_hop",
    default=None,
    help=(
        "Run filter LLM, entity LLM, and graph population once per version hop so "
        "every hop becomes its own Version node with only its own rules. "
        "Defaults to the HOP_BY_HOP env var (off)."
    ),
)
@click.option(
    "--skip-triage",
    is_flag=True,
    help="Keep every row. Do not call the System-1 classifier or apply triage rules.",
)
@click.option(
    "--force-triage",
    is_flag=True,
    help="Ignore the triage answer cache and any triage columns already in the raw file.",
)
@click.option(
    "--retriage-from-cache",
    is_flag=True,
    help="Recompute keep/drop from cached classifier probabilities without new HTTP calls.",
)
@click.option(
    "--skip-research",
    is_flag=True,
    help="Do not research filtered rows. The entity step sees the filtered Markdown only.",
)
@click.option(
    "--force-research",
    is_flag=True,
    help="Ignore the research row cache and any existing research.jsonl.",
)
@click.option(
    "--stop-after-research",
    is_flag=True,
    help=(
        "Run extraction, triage, and per-row research, then stop. "
        "No filter LLM, no entity LLM, and no graph writes."
    ),
)
@click.option(
    "--entity-source",
    type=click.Choice(["dossier", "filter"]),
    default=None,
    help=(
        "Where entities come from. 'dossier' builds them from research dossiers "
        "(the default when research is enabled). 'filter' is the filter LLM, then "
        "the entity LLM. Env: ENTITY_SOURCE."
    ),
)
@click.option(
    "--stop-after-clusters",
    is_flag=True,
    help=(
        "Run the action gate and clustering, write runs/clusters/, then stop. "
        "No entity calls and no graph writes, so no MODEL_* is needed."
    ),
)
@click.option(
    "--skip-signals",
    is_flag=True,
    help=(
        "Do not classify rules with System-1. Rules are written without the "
        "signal properties, which the planner reads as 'behavioral'."
    ),
)
@click.option(
    "--force-signals",
    is_flag=True,
    help="Ignore the rule-signal answer cache and ask System-1 again.",
)
@click.option("--output-md", type=click.Path(path_type=Path), default=None)
@click.option("--output-filtered-md", type=click.Path(path_type=Path), default=None)
@click.option("--output-json", type=click.Path(path_type=Path), default=None)
def pipeline(
    framework: str,
    from_version: str,
    to_version: str,
    force: bool,
    force_extract: bool,
    force_llm: bool,
    dry_run: bool,
    skip_existing: bool,
    extract_only: bool,
    hop_granularity: str | None,
    hop_by_hop: bool | None,
    skip_triage: bool,
    force_triage: bool,
    retriage_from_cache: bool,
    skip_research: bool,
    force_research: bool,
    stop_after_research: bool,
    entity_source: str | None,
    stop_after_clusters: bool,
    skip_signals: bool,
    force_signals: bool,
    output_md: Path | None,
    output_filtered_md: Path | None,
    output_json: Path | None,
) -> None:
    """Extract, filter, research, entity-extract, and optionally populate the graph."""
    if skip_research and force_research:
        raise click.ClickException(
            "--skip-research cannot be combined with --force-research"
        )
    if stop_after_research and (extract_only or skip_research):
        raise click.ClickException(
            "--stop-after-research cannot be combined with --extract-only or --skip-research"
        )
    if stop_after_research and not load_research_settings().enabled:
        raise click.ClickException(
            "--stop-after-research needs research enabled: set RESEARCH_BASE_URL and "
            "RESEARCH_MODEL_ID (TAVILY_API_KEY is optional)"
        )
    if stop_after_clusters and (extract_only or stop_after_research):
        raise click.ClickException(
            "--stop-after-clusters cannot be combined with --extract-only or "
            "--stop-after-research"
        )
    if skip_signals and force_signals:
        raise click.ClickException(
            "--skip-signals cannot be combined with --force-signals"
        )
    try:
        entity_source = resolve_entity_source(
            entity_source,
            skip_research=skip_research,
            research_enabled=load_research_settings().enabled,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    try:
        extractor = get_extractor(framework)
    except ValueError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc

    display_name = FRAMEWORK_DISPLAY_NAMES.get(framework, framework)
    from_version, to_version = _resolve_version_args(framework, from_version, to_version)

    try:
        granularity, by_hop = _resolve_hop_settings(hop_granularity, hop_by_hop)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    ensure_runs_directories()

    if by_hop:
        if output_md or output_filtered_md or output_json:
            raise click.ClickException(
                "--hop-by-hop derives one artifact set per version hop; "
                "drop --output-md, --output-filtered-md, and --output-json."
            )
        _run_hop_by_hop(
            extractor=extractor,
            framework=framework,
            display_name=display_name,
            from_version=from_version,
            to_version=to_version,
            granularity=granularity,
            extract_only=extract_only,
            dry_run=dry_run,
            skip_existing=skip_existing,
            force=force,
            force_extract=force_extract,
            force_llm=force_llm,
            skip_triage=skip_triage,
            force_triage=force_triage,
            retriage_from_cache=retriage_from_cache,
            skip_research=skip_research,
            force_research=force_research,
            stop_after_research=stop_after_research,
            entity_source=entity_source,
            stop_after_clusters=stop_after_clusters,
            skip_signals=skip_signals,
            force_signals=force_signals,
        )
        return

    raw_path = output_md or default_raw_md_path(framework, from_version, to_version)
    filtered_path = (
        output_filtered_md
        or default_filtered_md_path(framework, from_version, to_version)
    )
    json_path = output_json or default_entities_json_path(
        framework, from_version, to_version
    )

    if skip_existing:
        if (
            raw_path.exists()
            and filtered_path.exists()
            and pipeline_queries.version_exists(display_name, to_version)
        ):
            click.echo(
                f"Skipping {framework} {from_version} → {to_version}: "
                "raw MD, filtered MD, and Version node already exist."
            )
            return

    flags = resolve_cache_flags(
        raw_path=raw_path,
        filtered_path=filtered_path,
        json_path=json_path,
        force=force,
        force_extract=force_extract,
        force_llm=force_llm,
    )

    needs_llm = (
        not extract_only
        and not stop_after_research
        and not stop_after_clusters
        and entity_source == "filter"
        and not (flags.skip_filter_llm and flags.skip_entity_llm)
    )
    if needs_llm:
        _validate_model_provider()

    existing_raw: str | None = None
    hop_changes = None
    range_metadata = None
    if retriage_from_cache:
        if not raw_path.exists():
            raise click.ClickException(
                f"--retriage-from-cache requires an existing raw Markdown file at {raw_path}"
            )
        existing_raw = raw_path.read_text(encoding="utf-8")
    elif flags.skip_extraction:
        existing_raw = raw_path.read_text(encoding="utf-8")
    else:

        async def _run_extraction():
            async with extractor:
                return await extractor.extract_range(
                    from_version, to_version, granularity
                )

        try:
            result, hop_changes = asyncio.run(_run_extraction())
        except NotImplementedError as exc:
            click.echo(str(exc), err=True)
            raise SystemExit(1) from exc
        except (RuntimeError, ValueError) as exc:
            click.echo(str(exc), err=True)
            raise SystemExit(1) from exc
        range_metadata = result.metadata

    prepared = _materialize_raw(
        framework=framework,
        display_name=display_name,
        from_version=from_version,
        to_version=to_version,
        hop_changes=hop_changes,
        existing_raw=existing_raw,
        range_metadata=range_metadata,
        raw_path=raw_path,
        skip_triage=skip_triage,
        force_triage=force_triage,
        retriage_from_cache=retriage_from_cache,
    )

    if extract_only:
        click.echo(
            f"Extract-only complete — raw Markdown written to {raw_path} "
            f"({len(prepared.raw_md.splitlines())} lines). Filter and entity LLM steps skipped."
        )
        return

    extraction_result = _research_filter_extract(
        flags=flags,
        filter_md=prepared.filter_md,
        raw_md=prepared.raw_md,
        filtered_path=filtered_path,
        json_path=json_path,
        framework_key=framework,
        display_name=display_name,
        from_version=from_version,
        to_version=to_version,
        skip_research=skip_research,
        force_research=force_research,
        stop_after_research=stop_after_research,
        entity_source=entity_source,
        stop_after_clusters=stop_after_clusters,
        force_llm=force_llm,
    )
    if stop_after_research:
        click.echo(
            "Stopped after research — dossiers → runs/research/. "
            "Filter LLM, entity LLM, and graph skipped."
        )
        return
    if stop_after_clusters:
        click.echo(
            "Stopped after clusters — gate and clustering → runs/clusters/. "
            "Entity LLM and graph skipped."
        )
        return
    if extraction_result.failed_clusters:
        click.echo(
            f"{extraction_result.failed_clusters} entity cluster(s) failed; artifacts "
            "written, graph not populated. Re-run to retry them from the cache.",
            err=True,
        )
        raise SystemExit(3)

    result = populate_graph(
        batch=extraction_result.batch,
        framework_display=display_name,
        framework_key=framework,
        to_version=to_version,
        from_version=from_version,
        raw_md_path=str(raw_path),
        filtered_md_path=str(filtered_path),
        entities_json_path=str(json_path),
        dry_run=dry_run,
        skip_signals=skip_signals,
        force_signals=force_signals,
    )

    if dry_run:
        click.echo("Dry run complete — artifacts written; graph untouched.")
    elif result.skipped:
        click.echo("Graph population skipped (version already exists or dry-run).")
    else:
        click.echo(
            f"Graph populated: {result.rules_written} rules, "
            f"{result.steps_written} steps, {result.entities_written} entities"
            + _signal_note(result)
            + "."
        )


export_extract_populate_framework = pipeline

main.add_command(pipeline, name="export-extract-populate-framework")
main.add_command(pipeline, name="pipeline")

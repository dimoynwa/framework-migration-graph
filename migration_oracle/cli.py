"""CLI entry point for the migration oracle pipeline."""

from __future__ import annotations

import asyncio
from pathlib import Path

import click

from migration_oracle import config
from migration_oracle.pipeline.extractors import (
    FRAMEWORK_DISPLAY_NAMES,
    get_extractor,
    render_raw_markdown,
)
from migration_oracle.graph.queries import pipeline as pipeline_queries
from migration_oracle.pipeline._cache import resolve_cache_flags
from migration_oracle.pipeline._paths import (
    default_entities_json_path,
    default_filtered_md_path,
    default_raw_md_path,
    ensure_runs_directories,
)
from migration_oracle.pipeline.extractor import run_extraction
from migration_oracle.pipeline.extractors.base import HopContext, HopResult
from migration_oracle.pipeline.extractors.parsing import (
    HOP_GRANULARITIES,
    validate_hop_granularity,
)
from migration_oracle.models.graph import is_prerelease
from migration_oracle.pipeline.filters import emit_stale_warnings, run_filter
from migration_oracle.pipeline.populator import populate_graph


def _validate_model_provider() -> None:
    if not config.MODEL_PROVIDER.strip():
        raise click.ClickException(
            "MODEL_PROVIDER is not set. Set MODEL_PROVIDER to one of: "
            "bedrock, openai, anthropic, ollama, litellm, google."
        )


def _resolve_hop_settings(
    hop_granularity: str | None, hop_by_hop: bool | None
) -> tuple[str, bool]:
    """Resolve hop granularity/hop-by-hop mode from CLI flags with env fallback."""
    granularity = validate_hop_granularity(hop_granularity or config.HOP_GRANULARITY)
    by_hop = config.HOP_BY_HOP if hop_by_hop is None else hop_by_hop
    return granularity, by_hop


def _render_hop_markdown(
    framework: str,
    display_name: str,
    hop: HopResult,
) -> str:
    return render_raw_markdown(
        framework_key=framework,
        framework_display=display_name,
        from_version=hop.from_version,
        to_version=hop.to_version,
        hop_changes=[(hop.from_version, hop.to_version, hop.changes)],
        metadata=hop.result.metadata,
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

    async def _plan_and_extract() -> tuple[
        list[HopContext], dict[tuple[str, str], HopResult]
    ]:
        async with extractor:
            contexts = await extractor.plan_hops(
                from_version, to_version, granularity
            )
            pending = [
                context
                for context in contexts
                if force
                or force_extract
                or not raw_path_for(context).exists()
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

        flags = resolve_cache_flags(
            raw_path=raw_path,
            filtered_path=filtered_path,
            json_path=json_path,
            force=force,
            force_extract=force_extract,
            force_llm=force_llm,
        )
        emit_stale_warnings(flags)

        hop = extracted.get((hop_from, hop_to))
        if flags.skip_extraction and raw_path.exists():
            raw_md = raw_path.read_text(encoding="utf-8")
        elif hop is None or not hop.changes:
            click.echo(
                f"  · {hop_from} → {hop_to}: no documented changes, "
                "LLM and graph steps skipped."
            )
            hops_skipped += 1
            continue
        else:
            raw_md = _render_hop_markdown(framework, display_name, hop)
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(raw_md, encoding="utf-8")

        if extract_only:
            click.echo(
                f"  · {hop_from} → {hop_to}: raw Markdown "
                f"({len(raw_md.splitlines())} lines) → {raw_path}"
            )
            hops_done += 1
            continue

        if not (flags.skip_filter_llm and flags.skip_entity_llm):
            _validate_model_provider()
        filter_result = run_filter(
            raw_md, output_path=filtered_path, flags=flags
        )
        extraction_result = run_extraction(
            filter_result.filtered_md,
            framework_display=display_name,
            output_path=json_path,
            flags=flags,
        )
        result = populate_graph(
            batch=extraction_result.batch,
            framework_display=display_name,
            to_version=hop_to,
            from_version=hop_from,
            raw_md_path=str(raw_path),
            filtered_md_path=str(filtered_path),
            entities_json_path=str(json_path),
            dry_run=dry_run,
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
            f"{result.steps_written} steps, {result.entities_written} entities."
        )

    if extract_only:
        click.echo(
            f"Extract-only complete — {hops_done} hop(s) written to "
            f"runs/raw/, {hops_skipped} skipped."
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
@click.option("--force-llm", is_flag=True, help="Re-run filter and entity LLM steps.")
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
        "Version step size between ingestion hops: 'patch' (every release, "
        "default) or 'minor' (one hop per minor line). "
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
    output_md: Path | None,
    output_filtered_md: Path | None,
    output_json: Path | None,
) -> None:
    """Extract, filter, entity-extract, and optionally populate the graph."""
    try:
        extractor = get_extractor(framework)
    except ValueError as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(1) from exc

    display_name = FRAMEWORK_DISPLAY_NAMES.get(framework, framework)

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

    needs_llm = not (flags.skip_filter_llm and flags.skip_entity_llm)
    if needs_llm:
        _validate_model_provider()

    emit_stale_warnings(flags)

    if flags.skip_extraction:
        raw_md = raw_path.read_text(encoding="utf-8")
    else:

        async def _run_extraction() -> str:
            async with extractor:
                result, hop_changes = await extractor.extract_range(
                    from_version, to_version, granularity
                )
                return render_raw_markdown(
                    framework_key=framework,
                    framework_display=display_name,
                    from_version=from_version,
                    to_version=to_version,
                    hop_changes=hop_changes,
                    metadata=result.metadata,
                )

        try:
            raw_md = asyncio.run(_run_extraction())
        except NotImplementedError as exc:
            click.echo(str(exc), err=True)
            raise SystemExit(1) from exc
        except (RuntimeError, ValueError) as exc:
            click.echo(str(exc), err=True)
            raise SystemExit(1) from exc
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(raw_md, encoding="utf-8")

    if extract_only:
        click.echo(
            f"Extract-only complete — raw Markdown written to {raw_path} "
            f"({len(raw_md.splitlines())} lines). Filter and entity LLM steps skipped."
        )
        return

    filter_result = run_filter(raw_md, output_path=filtered_path, flags=flags)
    extraction_result = run_extraction(
        filter_result.filtered_md,
        framework_display=display_name,
        output_path=json_path,
        flags=flags,
    )

    result = populate_graph(
        batch=extraction_result.batch,
        framework_display=display_name,
        to_version=to_version,
        from_version=from_version,
        raw_md_path=str(raw_path),
        filtered_md_path=str(filtered_path),
        entities_json_path=str(json_path),
        dry_run=dry_run,
    )

    if dry_run:
        click.echo("Dry run complete — artifacts written; graph untouched.")
    elif result.skipped:
        click.echo("Graph population skipped (version already exists or dry-run).")
    else:
        click.echo(
            f"Graph populated: {result.rules_written} rules, "
            f"{result.steps_written} steps, {result.entities_written} entities."
        )


export_extract_populate_framework = pipeline

main.add_command(pipeline, name="export-extract-populate-framework")
main.add_command(pipeline, name="pipeline")

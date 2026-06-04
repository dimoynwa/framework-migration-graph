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
from migration_oracle.pipeline.filters import emit_stale_warnings, run_filter
from migration_oracle.pipeline.populator import populate_graph


def _validate_model_provider() -> None:
    if not config.MODEL_PROVIDER.strip():
        raise click.ClickException(
            "MODEL_PROVIDER is not set. Set MODEL_PROVIDER to one of: "
            "bedrock, openai, anthropic, ollama, litellm, google."
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

    ensure_runs_directories()

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
                    from_version, to_version
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

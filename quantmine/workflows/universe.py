"""Daily index-membership refresh workflow."""

from datetime import date

from sqlalchemy.engine import Engine

from ..storage.membership import (
    DEFAULT_INDEX,
    apply_diff,
    fetch_open_spells,
    seed_baseline,
)
from ..universe import (
    DEFAULT_GRACE_SCRAPES,
    MAX_PLAUSIBLE_DAILY_CHANGE,
    UniverseDiff,
    diff_universe,
    fetch_wiki_members,
)


def refresh_universe(
    engine: Engine,
    as_of: date,
    *,
    index_name: str = DEFAULT_INDEX,
    grace_scrapes: int = DEFAULT_GRACE_SCRAPES,
    max_change: int | None = MAX_PLAUSIBLE_DAILY_CHANGE,
    source: str = "wikipedia",
    members: set[str] | None = None,
    dry_run: bool = False,
) -> tuple[UniverseDiff, dict[str, int]]:
    """Scrape today's constituents and fold the changes into the membership table.

    Args:
        engine: Database engine.
        as_of: Date the scrape describes.
        index_name: Index to refresh.
        grace_scrapes: Consecutive absences tolerated before closing a spell.
        max_change: Refuse to write above this many real changes; None disables.
        source: Provenance recorded on newly opened spells.
        members: Pre-fetched constituent list, bypassing the network. Used by
            tests and by the one-off importer.
        dry_run: Compute the diff and skip the write.

    Returns:
        The diff and the per-kind counts. On a dry run these describe what
        *would* be written rather than being zeroed -- reporting zeros there
        made the summary line say "0 confirmed" for a healthy 503-member scrape,
        which is indistinguishable from a scrape that found nothing.

    Raises:
        UniverseSanityError: If the scrape or the implied change count fails its
            plausibility checks. Nothing is written in that case.
    """
    observed = fetch_wiki_members() if members is None else members
    spells = fetch_open_spells(engine, index_name)
    if not spells and not dry_run:
        # Never-seeded table. Diffing today's scrape against nothing would open
        # a spell starting today for all ~500 members, and the downloader sizes
        # its history request off start_date -- so every research window before
        # this week would come back empty for the life of the install. Lay the
        # vendored baseline down first; the diff below then does its normal job
        # of carrying it forward to today.
        seeded = seed_baseline(engine, index_name=index_name)
        if seeded:
            spells = fetch_open_spells(engine, index_name)
    diff = diff_universe(
        spells,
        observed,
        as_of,
        grace_scrapes=grace_scrapes,
        max_change=max_change,
    )
    if dry_run:
        return diff, {
            "opened": len(diff.opened),
            "confirmed": len(diff.confirmed),
            "pending": len(diff.pending),
            "closed": len(diff.closed),
        }
    counts = apply_diff(
        engine, diff, as_of, index_name=index_name, source=source
    )
    return diff, counts

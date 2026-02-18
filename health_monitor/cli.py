import click
from datetime import datetime, timezone, date
from rich.console import Console
from rich.table import Table
from rich import box

from .db import init_db, insert_event, query_events

console = Console()

TAGS = ["food", "activity", "symptom", "mood", "stress", "sleep", "other"]


@click.group()
def main():
    """Health event tracker. Log what you eat, do, and feel."""
    init_db()


# ---------------------------------------------------------------------------
# hm log
# ---------------------------------------------------------------------------

@main.command()
@click.argument("tag", type=click.Choice(TAGS))
@click.argument("value")
@click.option("--category", "-c", default=None, help="Category (e.g. regular, junk)")
@click.option("--notes", "-n", default=None, help="Extra notes")
def log(tag, value, category, notes):
    """Log a structured event.

    \b
    Examples:
      hm log food avocado --category regular
      hm log food alcohol --category junk
      hm log activity gaming --notes "2h"
      hm log mood relaxed
      hm log stress 7
    """
    event_id = insert_event(tag=tag, category=category, value=value, notes=notes)
    console.print(f"[green]✓[/green] Logged [bold]{tag}[/bold] → {value}"
                  + (f"  [dim]({category})[/dim]" if category else "")
                  + f"  [dim]id={event_id}[/dim]")


# ---------------------------------------------------------------------------
# hm symptom  (shortcut for common symptom logging)
# ---------------------------------------------------------------------------

@main.command()
@click.argument("symptom", default="face_redness")
@click.argument("score", type=click.IntRange(0, 10))
@click.option("--notes", "-n", default=None)
def symptom(symptom, score, notes):
    """Log a symptom severity score (0–10).

    \b
    Examples:
      hm symptom face_redness 6
      hm symptom face_redness 3 --notes "after breakfast"
    """
    event_id = insert_event(
        tag="symptom",
        category=symptom,
        value=str(score),
        notes=notes,
    )
    bar = _score_bar(score)
    console.print(f"[green]✓[/green] Symptom [bold]{symptom}[/bold]: {score}/10  {bar}  [dim]id={event_id}[/dim]")


# ---------------------------------------------------------------------------
# hm list
# ---------------------------------------------------------------------------

@main.command("list")
@click.option("--tag", "-t", default=None, type=click.Choice(TAGS + [None]), help="Filter by tag")
@click.option("--today", is_flag=True, help="Only show today's events")
@click.option("--limit", "-l", default=20, show_default=True)
def list_events(tag, today, limit):
    """List recent events."""
    since = None
    if today:
        since = date.today().isoformat()

    rows = query_events(tag=tag, since=since, limit=limit)

    if not rows:
        console.print("[dim]No events found.[/dim]")
        return

    table = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
    table.add_column("Time", style="dim", width=19)
    table.add_column("Tag", width=10)
    table.add_column("Category", width=14)
    table.add_column("Value", width=20)
    table.add_column("Notes")

    for row in rows:
        ts = _fmt_ts(row["timestamp"])
        value = row["value"] or ""
        if row["tag"] == "symptom":
            try:
                value = f"{value}/10  {_score_bar(int(value))}"
            except (ValueError, TypeError):
                pass
        table.add_row(
            ts,
            _tag_color(row["tag"]),
            row["category"] or "",
            value,
            row["notes"] or "",
        )

    console.print(table)
    console.print(f"[dim]{len(rows)} event(s)[/dim]")


# ---------------------------------------------------------------------------
# hm today
# ---------------------------------------------------------------------------

@main.command()
def today():
    """Summary of today's events."""
    since = date.today().isoformat()
    rows = query_events(since=since, limit=200)

    if not rows:
        console.print("[dim]No events logged today yet.[/dim]")
        return

    by_tag: dict[str, list] = {}
    for row in rows:
        by_tag.setdefault(row["tag"], []).append(row)

    console.print(f"\n[bold]Today — {date.today()}[/bold]\n")
    for tag, events in sorted(by_tag.items()):
        console.print(f"  [bold cyan]{tag}[/bold cyan]")
        for e in events:
            val = e["value"] or ""
            cat = f"[dim]{e['category']}[/dim]  " if e["category"] else ""
            console.print(f"    {cat}{val}" + (f"  [dim italic]{e['notes']}[/dim italic]" if e["notes"] else ""))
    console.print()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_bar(score: int) -> str:
    filled = round(score / 2)
    return "█" * filled + "░" * (5 - filled)


def _fmt_ts(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts).astimezone()
        return dt.strftime("%m-%d %H:%M")
    except Exception:
        return ts[:16]


def _tag_color(tag: str) -> str:
    colors = {
        "food":     "[green]food[/green]",
        "symptom":  "[red]symptom[/red]",
        "activity": "[blue]activity[/blue]",
        "mood":     "[yellow]mood[/yellow]",
        "stress":   "[magenta]stress[/magenta]",
        "sleep":    "[cyan]sleep[/cyan]",
    }
    return colors.get(tag, tag)

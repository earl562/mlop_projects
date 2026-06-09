from __future__ import annotations

import asyncio

import click
from rich.console import Console
from rich.table import Table

console = Console()


@click.group()
def main() -> None:
    """PlotLot Outreach Agent — autonomous prospect finding, pitching, and event scouting."""
    pass


@main.command()
@click.option("--goal", default=None, help="Natural language goal for this run.")
@click.option("--dry-run", is_flag=True, default=False, help="Draft emails but don't send.")
def run(goal: str | None, dry_run: bool) -> None:
    """Run the full outreach cycle (find → enrich → email → events → LinkedIn/Twitter queue)."""
    from outreach.agents.orchestrator import run_agent

    console.print("[bold green]Starting outreach cycle...[/bold green]")
    summary = asyncio.run(run_agent(goal=goal, dry_run=dry_run))
    console.print(f"\n[bold]Summary:[/bold]\n{summary}")


@main.command()
def scout() -> None:
    """Discover upcoming networking events relevant to PlotLot."""
    from outreach.agents.event_scout import scout_events
    from outreach.core.db import EventRow, SessionLocal, init_db

    async def _run() -> None:
        await init_db()
        events = await scout_events()
        async with SessionLocal() as session:
            for ev in events:
                row = EventRow(
                    name=ev.name, organizer=ev.organizer,
                    date=ev.date, location=ev.location,
                    url=ev.url, description=ev.description,
                    relevance_score=ev.relevance_score,
                )
                session.add(row)
            await session.commit()

        table = Table(title="Upcoming Events", show_lines=True)
        table.add_column("Event", style="cyan", max_width=40)
        table.add_column("Organizer", style="magenta")
        table.add_column("Location")
        table.add_column("Score", justify="right")
        table.add_column("URL", style="blue", max_width=40)
        for ev in events:
            table.add_row(ev.name, ev.organizer, ev.location, f"{ev.relevance_score:.2f}", ev.url or "")
        console.print(table)

    asyncio.run(_run())


@main.command()
@click.option("--icp", default=None, type=click.Choice(["residential", "datacenter", "press", "investor"]),
              help="Filter by ICP type.")
def find(icp: str | None) -> None:
    """Find new prospects and save them to the database."""
    from outreach.agents.prospect_finder import find_prospects
    from outreach.core.db import ProspectRow, SessionLocal, init_db
    from outreach.core.types import ICPType

    async def _run() -> None:
        await init_db()
        icp_types = [ICPType(icp)] if icp else None
        prospects = await find_prospects(icp_types=icp_types)

        async with SessionLocal() as session:
            saved = 0
            for p in prospects:
                if p.linkedin_url:
                    from sqlalchemy import select
                    existing = await session.execute(
                        select(ProspectRow).where(ProspectRow.linkedin_url == p.linkedin_url)
                    )
                    if existing.scalar_one_or_none():
                        continue
                row = ProspectRow(
                    name=p.name, first_name=p.first_name, last_name=p.last_name,
                    title=p.title, company=p.company, market=p.market,
                    icp_type=p.icp_type.value, linkedin_url=p.linkedin_url,
                    twitter_handle=p.twitter_handle, notes=p.notes, source="web_search",
                )
                session.add(row)
                saved += 1
            await session.commit()

        table = Table(title=f"Prospects Found ({len(prospects)})", show_lines=True)
        table.add_column("Name", style="cyan")
        table.add_column("Title")
        table.add_column("Company")
        table.add_column("Market")
        table.add_column("ICP")
        for p in prospects:
            table.add_row(p.name, p.title, p.company, p.market, p.icp_type.value)
        console.print(table)
        console.print(f"[green]Saved {saved} new prospects.[/green]")

    asyncio.run(_run())


@main.command()
@click.option("--dry-run", is_flag=True, default=False)
def email(dry_run: bool) -> None:
    """Send cold emails to queued prospects with verified email addresses."""
    from outreach.agents.email_agent import run_email_campaign
    from outreach.core.db import SessionLocal, init_db

    async def _run() -> None:
        await init_db()
        async with SessionLocal() as session:
            results = await run_email_campaign(session, dry_run=dry_run)

        table = Table(title="Email Campaign Results", show_lines=True)
        table.add_column("Prospect")
        table.add_column("Email")
        table.add_column("Subject")
        table.add_column("Status")
        for r in results:
            status_color = "green" if r["status"] == "sent" else "yellow" if r["status"] == "dry_run" else "red"
            table.add_row(r["prospect"], r.get("email", ""), r.get("subject", ""),
                          f"[{status_color}]{r['status']}[/{status_color}]")
        console.print(table)

    asyncio.run(_run())


@main.command("smtp-setup")
def smtp_setup() -> None:
    """Check Gmail SMTP + App Password configuration and show setup instructions."""
    from outreach.config import settings

    if settings.smtp_user and settings.smtp_password:
        masked_user = settings.smtp_user[:4] + "..." + settings.smtp_user[-4:]
        masked_pw = settings.smtp_password[:4] + "..." + settings.smtp_password[-4:]
        console.print(f"[green]✓[/green] SMTP_USER: {masked_user}")
        console.print(f"[green]✓[/green] SMTP_PASSWORD: {masked_pw}")
    else:
        console.print("[red]✗[/red] SMTP_USER or SMTP_PASSWORD is not set")
        console.print()
        console.print("To set up Gmail SMTP with App Password:")
        console.print("  1. Enable 2-Step Verification at [blue]https://myaccount.google.com/security[/blue]")
        console.print("  2. Generate an App Password at [blue]https://myaccount.google.com/apppasswords[/blue]")
        console.print("  3. Add to your .env file:")
        console.print("     [bold]SMTP_USER=your.email@gmail.com[/bold]")
        console.print("     [bold]SMTP_PASSWORD=your-16-char-app-password[/bold]")
        console.print()
        console.print("Note: App Passwords are 16 characters, generated once per device.")
        console.print("They are NOT your regular Gmail password.")

    console.print(f"[green]✓[/green] SMTP_HOST: {settings.smtp_host}:{settings.smtp_port}")
    console.print(f"[green]✓[/green] SMTP_FROM_EMAIL: {settings.smtp_from_email or settings.smtp_user or '(not set)'}")


@main.command("linkedin-auth")
@click.option("--email-addr", prompt="LinkedIn email")
@click.option("--password", prompt=True, hide_input=True)
@click.option("--output", default="linkedin_session.json")
def linkedin_auth(email_addr: str, password: str, output: str) -> None:
    """Log in to LinkedIn and save session state for Playwright automation."""
    from outreach.tools.linkedin import save_linkedin_session
    asyncio.run(save_linkedin_session(email_addr, password, output))


@main.command()
def status() -> None:
    """Show current pipeline status."""
    from outreach.core.db import ProspectRow, SessionLocal, init_db
    from outreach.core.types import ProspectStatus
    from sqlalchemy import func, select

    async def _run() -> None:
        await init_db()
        async with SessionLocal() as session:
            table = Table(title="Pipeline Status", show_lines=False)
            table.add_column("Status", style="cyan")
            table.add_column("Count", justify="right")
            for s in ProspectStatus:
                result = await session.execute(
                    select(func.count()).where(ProspectRow.status == s.value)
                )
                count = result.scalar() or 0
                table.add_row(s.value, str(count))
        console.print(table)

    asyncio.run(_run())


def scout_main() -> None:
    scout()


def email_main() -> None:
    email()


if __name__ == "__main__":
    main()

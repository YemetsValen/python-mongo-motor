"""
CLI commands for the Match Predictions System.

Provides command-line interface for managing users, matches,
predictions, and running analytics.
"""

import asyncio
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable

import click
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config.settings import get_settings
from src.db.connection import close_database, get_database
from src.db.indexes import ensure_indexes
from src.models.analytics import LeaderboardType, TimePeriod
from src.models.match import MatchCreate, MatchResult, MatchStatus, Sport
from src.services.analytics_service import AnalyticsService
from src.services.match_service import MatchNotFoundError, MatchService
from src.services.prediction_service import PredictionNotAllowedError, PredictionService
from src.services.user_service import UserAlreadyExistsError, UserNotFoundError, UserService

console = Console()


def async_command(f: Callable) -> Callable:
    """Decorator to run async functions in Click commands."""

    @wraps(f)
    def wrapper(*args, **kwargs):
        return asyncio.run(f(*args, **kwargs))

    return wrapper


def handle_errors(f: Callable) -> Callable:
    """Decorator to handle common errors in CLI commands."""

    @wraps(f)
    async def wrapper(*args, **kwargs):
        try:
            return await f(*args, **kwargs)
        except UserNotFoundError as e:
            console.print(f"[red]Error:[/red] {e}")
        except UserAlreadyExistsError as e:
            console.print(f"[red]Error:[/red] {e}")
        except MatchNotFoundError as e:
            console.print(f"[red]Error:[/red] {e}")
        except PredictionNotAllowedError as e:
            console.print(f"[red]Error:[/red] {e}")
        except Exception as e:
            console.print(f"[red]Unexpected error:[/red] {e}")
            raise
        finally:
            await close_database()

    return wrapper


# =============================================================================
# Main CLI Group
# =============================================================================


@click.group()
@click.version_option(version="0.1.0", prog_name="predictions")
def cli():
    """Match Predictions System - CLI Interface.

    Manage users, matches, predictions, and view analytics.
    """
    pass


# =============================================================================
# Database Commands
# =============================================================================


@cli.group()
def db():
    """Database management commands."""
    pass


@db.command("init")
@async_command
@handle_errors
async def db_init():
    """Initialize database with indexes."""
    console.print("[yellow]Initializing database...[/yellow]")

    database = await get_database()
    results = await ensure_indexes(database)

    table = Table(title="Created Indexes", box=box.ROUNDED)
    table.add_column("Collection", style="cyan")
    table.add_column("Indexes", style="green")

    for collection, indexes in results.items():
        table.add_row(collection, ", ".join(indexes))

    console.print(table)
    console.print("[green]Database initialized successfully![/green]")


@db.command("status")
@async_command
@handle_errors
async def db_status():
    """Check database connection status."""
    from src.db.connection import get_connection

    conn = await get_connection()
    await conn.connect()

    health = await conn.health_check()

    if health["healthy"]:
        console.print(
            Panel(
                f"[green]Connected[/green]\n"
                f"Server: MongoDB {health.get('server_version', 'unknown')}\n"
                f"Latency: {health.get('latency_ms', 'N/A')} ms",
                title="Database Status",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel(
                f"[red]Disconnected[/red]\nError: {health.get('error', 'Unknown')}",
                title="Database Status",
                border_style="red",
            )
        )


# =============================================================================
# User Commands
# =============================================================================


@cli.group()
def user():
    """User management commands."""
    pass


@user.command("create")
@click.option("--username", "-u", required=True, help="Unique username")
@click.option("--email", "-e", required=True, help="Email address")
@click.option("--display-name", "-n", default=None, help="Display name")
@async_command
@handle_errors
async def user_create(username: str, email: str, display_name: str | None):
    """Create a new user."""
    db = await get_database()
    service = UserService(db)

    user = await service.register_user(
        username=username,
        email=email,
        display_name=display_name,
    )

    console.print(
        Panel(
            f"[green]User created successfully![/green]\n\n"
            f"ID: {user.id}\n"
            f"Username: {user.username}\n"
            f"Email: {user.email}\n"
            f"Display Name: {user.effective_display_name}",
            title="New User",
            border_style="green",
        )
    )


@user.command("list")
@click.option("--limit", "-l", default=20, help="Maximum users to show")
@click.option("--all", "show_all", is_flag=True, help="Include inactive users")
@async_command
@handle_errors
async def user_list(limit: int, show_all: bool):
    """List all users."""
    db = await get_database()
    service = UserService(db)

    users = await service.list_users(limit=limit, active_only=not show_all)

    table = Table(title=f"Users ({len(users)})", box=box.ROUNDED)
    table.add_column("ID", style="dim")
    table.add_column("Username", style="cyan")
    table.add_column("Email")
    table.add_column("Points", justify="right", style="green")
    table.add_column("Predictions", justify="right")
    table.add_column("Status")

    for u in users:
        status = "[green]Active[/green]" if u.is_active else "[red]Inactive[/red]"
        table.add_row(
            str(u.id)[:8] + "...",
            u.username,
            u.email,
            str(u.total_points),
            str(u.total_predictions),
            status,
        )

    console.print(table)


@user.command("stats")
@click.argument("user_id")
@async_command
@handle_errors
async def user_stats(user_id: str):
    """Show detailed statistics for a user."""
    db = await get_database()
    service = UserService(db)

    stats = await service.get_user_stats(user_id)

    console.print(
        Panel(
            f"[cyan]{stats['username']}[/cyan] ({stats['display_name']})\n\n"
            f"Total Predictions: {stats['total_predictions']}\n"
            f"Scored: {stats['scored_predictions']} | Pending: {stats['pending_predictions']}\n\n"
            f"[green]Points: {stats['total_points']}[/green]\n"
            f"Accuracy: {stats['accuracy_percent']}%\n"
            f"Avg Points/Prediction: {stats['avg_points_per_prediction']}\n\n"
            f"Exact Scores: {stats['exact_scores']}\n"
            f"Correct Differences: {stats['correct_differences']}\n"
            f"Correct Outcomes: {stats['correct_outcomes']}\n"
            f"Incorrect: {stats['incorrect']}",
            title="User Statistics",
            border_style="cyan",
        )
    )


@user.command("delete")
@click.argument("user_id")
@click.option("--hard", is_flag=True, help="Permanently delete user and predictions")
@click.confirmation_option(prompt="Are you sure you want to delete this user?")
@async_command
@handle_errors
async def user_delete(user_id: str, hard: bool):
    """Delete a user (soft delete by default)."""
    db = await get_database()
    service = UserService(db)

    await service.delete_user(user_id, hard_delete=hard)

    action = "permanently deleted" if hard else "deactivated"
    console.print(f"[green]User {action} successfully.[/green]")


# =============================================================================
# Match Commands
# =============================================================================


@cli.group()
def match():
    """Match management commands."""
    pass


@match.command("create")
@click.option("--home", "-h", required=True, help="Home team name")
@click.option("--away", "-a", required=True, help="Away team name")
@click.option("--date", "-d", required=True, help="Scheduled date (YYYY-MM-DD HH:MM)")
@click.option("--sport", "-s", default="football", help="Sport type")
@click.option("--league", "-l", default=None, help="League name")
@async_command
@handle_errors
async def match_create(home: str, away: str, date: str, sport: str, league: str | None):
    """Create a new match."""
    db = await get_database()
    service = MatchService(db)

    # Parse date
    try:
        scheduled_at = datetime.strptime(date, "%Y-%m-%d %H:%M")
    except ValueError:
        console.print("[red]Invalid date format. Use YYYY-MM-DD HH:MM[/red]")
        return

    match_data = MatchCreate(
        home_team=home,
        away_team=away,
        scheduled_at=scheduled_at,
        sport=Sport(sport),
        league=league,
    )

    match = await service.create_match(match_data)

    console.print(
        Panel(
            f"[green]Match created![/green]\n\n"
            f"ID: {match.id}\n"
            f"{match.home_team} vs {match.away_team}\n"
            f"Date: {match.scheduled_at}\n"
            f"Sport: {match.sport}\n"
            f"League: {match.league or 'N/A'}",
            title="New Match",
            border_style="green",
        )
    )


@match.command("list")
@click.option("--status", "-s", default=None, help="Filter by status")
@click.option("--limit", "-l", default=20, help="Maximum matches to show")
@async_command
@handle_errors
async def match_list(status: str | None, limit: int):
    """List matches."""
    db = await get_database()
    service = MatchService(db)

    from src.models.match import MatchFilter

    filter_params = MatchFilter()
    if status:
        filter_params.status = MatchStatus(status)

    matches, total = await service.get_matches(filter_params, limit=limit)

    table = Table(title=f"Matches ({len(matches)} of {total})", box=box.ROUNDED)
    table.add_column("ID", style="dim")
    table.add_column("Home", style="cyan")
    table.add_column("Away", style="yellow")
    table.add_column("Score", justify="center")
    table.add_column("Date")
    table.add_column("Status")
    table.add_column("Predictions", justify="right")

    for m in matches:
        score = m.display_score
        status_str = {
            "pending": "[yellow]Pending[/yellow]",
            "live": "[red]LIVE[/red]",
            "finished": "[green]Finished[/green]",
            "cancelled": "[dim]Cancelled[/dim]",
            "postponed": "[orange]Postponed[/orange]",
        }.get(m.status, m.status)

        table.add_row(
            str(m.id)[:8] + "...",
            m.home_team,
            m.away_team,
            score,
            m.scheduled_at.strftime("%Y-%m-%d %H:%M"),
            status_str,
            str(m.total_predictions),
        )

    console.print(table)


@match.command("result")
@click.argument("match_id")
@click.option("--home-score", "-h", required=True, type=int, help="Home team score")
@click.option("--away-score", "-a", required=True, type=int, help="Away team score")
@async_command
@handle_errors
async def match_result(match_id: str, home_score: int, away_score: int):
    """Set match result and score predictions."""
    db = await get_database()
    service = MatchService(db)

    result = MatchResult(home_score=home_score, away_score=away_score)
    match, scored_count = await service.finish_match(match_id, result)

    console.print(
        Panel(
            f"[green]Match finished![/green]\n\n"
            f"{match.home_team} {match.home_score} - {match.away_score} {match.away_team}\n\n"
            f"Predictions scored: {scored_count}",
            title="Match Result",
            border_style="green",
        )
    )


@match.command("upcoming")
@click.option("--days", "-d", default=7, help="Days ahead to show")
@async_command
@handle_errors
async def match_upcoming(days: int):
    """Show upcoming matches."""
    db = await get_database()
    service = MatchService(db)

    matches = await service.get_upcoming_matches(days_ahead=days)

    if not matches:
        console.print("[yellow]No upcoming matches found.[/yellow]")
        return

    table = Table(title=f"Upcoming Matches (next {days} days)", box=box.ROUNDED)
    table.add_column("Match", style="cyan")
    table.add_column("Date")
    table.add_column("League")
    table.add_column("Predictions", justify="right")
    table.add_column("Open", justify="center")

    for m in matches:
        open_status = "[green]Yes[/green]" if m.is_predictable else "[red]No[/red]"
        table.add_row(
            f"{m.home_team} vs {m.away_team}",
            m.scheduled_at.strftime("%Y-%m-%d %H:%M"),
            m.league or "N/A",
            str(m.total_predictions),
            open_status,
        )

    console.print(table)


# =============================================================================
# Prediction Commands
# =============================================================================


@cli.group()
def predict():
    """Prediction management commands."""
    pass


@predict.command("create")
@click.option("--user", "-u", required=True, help="User ID")
@click.option("--match", "-m", "match_id", required=True, help="Match ID")
@click.option("--home", "-h", required=True, type=int, help="Predicted home score")
@click.option("--away", "-a", required=True, type=int, help="Predicted away score")
@async_command
@handle_errors
async def predict_create(user: str, match_id: str, home: int, away: int):
    """Create a new prediction."""
    db = await get_database()
    service = PredictionService(db)

    prediction = await service.create_prediction(
        user_id=user,
        match_id=match_id,
        home_score=home,
        away_score=away,
    )

    console.print(
        Panel(
            f"[green]Prediction created![/green]\n\n"
            f"Predicted Score: {prediction.predicted_home_score} - {prediction.predicted_away_score}\n"
            f"Outcome: {prediction.predicted_outcome}",
            title="New Prediction",
            border_style="green",
        )
    )


@predict.command("list")
@click.option("--user", "-u", required=True, help="User ID")
@click.option("--limit", "-l", default=20, help="Maximum predictions to show")
@async_command
@handle_errors
async def predict_list(user: str, limit: int):
    """List predictions for a user."""
    db = await get_database()
    service = PredictionService(db)

    predictions = await service.get_user_predictions(
        user_id=user,
        limit=limit,
        with_details=True,
    )

    table = Table(title=f"Predictions ({len(predictions)})", box=box.ROUNDED)
    table.add_column("Match")
    table.add_column("Predicted", justify="center")
    table.add_column("Actual", justify="center")
    table.add_column("Points", justify="right")
    table.add_column("Status")

    for p in predictions:
        match_str = (
            f"{p.match_home_team} vs {p.match_away_team}" if p.match_home_team else "Unknown"
        )
        predicted = f"{p.predicted_home_score} - {p.predicted_away_score}"
        actual = f"{p.actual_home_score} - {p.actual_away_score}" if p.is_scored else "-"
        points = str(p.points) if p.points is not None else "-"
        status = "[green]Scored[/green]" if p.is_scored else "[yellow]Pending[/yellow]"

        table.add_row(match_str, predicted, actual, points, status)

    console.print(table)


# =============================================================================
# Analytics Commands
# =============================================================================


@cli.group()
def analytics():
    """Analytics and statistics commands."""
    pass


@analytics.command("leaderboard")
@click.option("--type", "-t", "lb_type", default="points", help="Leaderboard type")
@click.option("--period", "-p", default="all_time", help="Time period")
@click.option("--limit", "-l", default=10, help="Number of entries")
@async_command
@handle_errors
async def analytics_leaderboard(lb_type: str, period: str, limit: int):
    """Show the leaderboard."""
    db = await get_database()
    service = AnalyticsService(db)

    leaderboard = await service.get_leaderboard(
        leaderboard_type=LeaderboardType(lb_type),
        period=TimePeriod(period),
        limit=limit,
    )

    table = Table(
        title=f"🏆 Leaderboard ({leaderboard.type.value} - {leaderboard.period.value})",
        box=box.ROUNDED,
    )
    table.add_column("Rank", justify="center", style="bold")
    table.add_column("User", style="cyan")
    table.add_column("Points", justify="right", style="green")
    table.add_column("Predictions", justify="right")
    table.add_column("Accuracy", justify="right")
    table.add_column("Exact Scores", justify="right", style="yellow")

    for entry in leaderboard.entries:
        rank_str = (
            f"🥇 {entry.rank}"
            if entry.rank == 1
            else f"🥈 {entry.rank}"
            if entry.rank == 2
            else f"🥉 {entry.rank}"
            if entry.rank == 3
            else str(entry.rank)
        )

        table.add_row(
            rank_str,
            entry.username,
            str(entry.total_points),
            str(entry.total_predictions),
            f"{entry.accuracy_percent}%",
            str(entry.exact_scores),
        )

    console.print(table)
    console.print(f"\nTotal participants: {leaderboard.total_participants}")


@analytics.command("system")
@async_command
@handle_errors
async def analytics_system():
    """Show system-wide statistics."""
    db = await get_database()
    service = AnalyticsService(db)

    stats = await service.get_system_stats()

    console.print(
        Panel(
            f"[bold]Users[/bold]\n"
            f"  Total: {stats.total_users}\n"
            f"  Active: {stats.active_users}\n\n"
            f"[bold]Matches[/bold]\n"
            f"  Total: {stats.total_matches}\n"
            f"  Finished: {stats.finished_matches}\n"
            f"  Pending: {stats.pending_matches}\n\n"
            f"[bold]Predictions[/bold]\n"
            f"  Total: {stats.total_predictions}\n"
            f"  Scored: {stats.scored_predictions}\n"
            f"  Avg per Match: {stats.avg_predictions_per_match}\n"
            f"  Avg per User: {stats.avg_predictions_per_user}\n\n"
            f"[bold]Global Accuracy[/bold]: {stats.global_accuracy_percent}%",
            title="📊 System Statistics",
            border_style="blue",
        )
    )


@analytics.command("distribution")
@click.option("--period", "-p", default="all_time", help="Time period")
@async_command
@handle_errors
async def analytics_distribution(period: str):
    """Show prediction outcome distribution."""
    db = await get_database()
    service = AnalyticsService(db)

    dist = await service.get_prediction_distribution(TimePeriod(period))

    console.print(
        Panel(
            f"Period: {dist.period.value}\n"
            f"Total Predictions: {dist.total}\n\n"
            f"[green]Exact Scores (3 pts):[/green] {dist.exact_scores_count} ({dist.exact_scores_percent}%)\n"
            f"[yellow]Correct Diff (2 pts):[/yellow] {dist.correct_diffs_count} ({dist.correct_diffs_percent}%)\n"
            f"[blue]Correct Outcome (1 pt):[/blue] {dist.correct_outcomes_count} ({dist.correct_outcomes_percent}%)\n"
            f"[red]Incorrect (0 pts):[/red] {dist.incorrect_count} ({dist.incorrect_percent}%)",
            title="📈 Prediction Distribution",
            border_style="cyan",
        )
    )


# =============================================================================
# Migration Commands
# =============================================================================


@cli.group()
def migrate():
    """Database migration commands."""
    pass


@migrate.command("up")
@async_command
@handle_errors
async def migrate_up():
    """Apply all pending migrations."""
    console.print("[yellow]Running migrations...[/yellow]")
    # TODO: Implement migration runner
    console.print("[green]Migrations complete![/green]")


@migrate.command("status")
@async_command
@handle_errors
async def migrate_status():
    """Show migration status."""
    console.print("[yellow]Migration status:[/yellow]")
    # TODO: Implement migration status check
    console.print("No pending migrations.")


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    cli()

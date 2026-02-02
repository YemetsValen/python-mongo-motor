"""
Match Predictions System - Main Entry Point

This is the main application entry point that demonstrates
the usage of the predictions system with MongoDB and Motor.
"""

import asyncio
import sys
from datetime import datetime, timedelta

import structlog
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config.settings import get_settings
from src.db.connection import close_database, get_connection, get_database
from src.db.indexes import ensure_indexes
from src.models.match import MatchCreate, MatchResult, Sport
from src.models.user import UserCreate
from src.services.analytics_service import AnalyticsService
from src.services.match_service import MatchService
from src.services.prediction_service import PredictionService
from src.services.user_service import UserService

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(colors=True),
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)
console = Console()


async def check_connection() -> bool:
    """Check MongoDB connection health."""
    try:
        connection = await get_connection()
        await connection.connect()
        health = await connection.health_check()

        if health["healthy"]:
            console.print(
                f"[green]✓[/green] Connected to MongoDB "
                f"(version: {health.get('server_version', 'unknown')}, "
                f"latency: {health.get('latency_ms', 'N/A')}ms)"
            )
            return True
        else:
            console.print(f"[red]✗[/red] MongoDB unhealthy: {health.get('error', 'Unknown error')}")
            return False
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to connect to MongoDB: {e}")
        return False


async def setup_indexes() -> None:
    """Create database indexes."""
    db = await get_database()
    console.print("[yellow]Creating indexes...[/yellow]")

    results = await ensure_indexes(db)

    for collection, indexes in results.items():
        console.print(f"  [green]✓[/green] {collection}: {len(indexes)} indexes")


async def demo_create_users(user_service: UserService) -> list:
    """Create demo users."""
    console.print("\n[bold cyan]Creating demo users...[/bold cyan]")

    users_data = [
        ("pro_predictor", "pro@example.com", "Pro Predictor"),
        ("lucky_guesser", "lucky@example.com", "Lucky Guesser"),
        ("stats_master", "stats@example.com", "Stats Master"),
        ("newbie_fan", "newbie@example.com", "Newbie Fan"),
    ]

    users = []
    for username, email, display_name in users_data:
        try:
            user = await user_service.register_user(
                username=username,
                email=email,
                display_name=display_name,
            )
            users.append(user)
            console.print(f"  [green]✓[/green] Created user: {username}")
        except Exception as e:
            # User might already exist
            try:
                user = await user_service.get_user_by_username(username)
                users.append(user)
                console.print(f"  [yellow]○[/yellow] User exists: {username}")
            except Exception:
                console.print(f"  [red]✗[/red] Failed to create {username}: {e}")

    return users


async def demo_create_matches(match_service: MatchService) -> list:
    """Create demo matches."""
    console.print("\n[bold cyan]Creating demo matches...[/bold cyan]")

    now = datetime.utcnow()

    matches_data = [
        ("Manchester United", "Liverpool", now + timedelta(days=1), "Premier League"),
        ("Real Madrid", "Barcelona", now + timedelta(days=2), "La Liga"),
        ("Bayern Munich", "Borussia Dortmund", now + timedelta(days=3), "Bundesliga"),
        ("Juventus", "AC Milan", now + timedelta(days=4), "Serie A"),
        ("PSG", "Marseille", now + timedelta(days=5), "Ligue 1"),
    ]

    matches = []
    for home, away, scheduled, league in matches_data:
        try:
            match_data = MatchCreate(
                home_team=home,
                away_team=away,
                scheduled_at=scheduled,
                sport=Sport.FOOTBALL,
                league=league,
                season="2024-25",
            )
            match = await match_service.create_match(match_data)
            matches.append(match)
            console.print(f"  [green]✓[/green] Created match: {home} vs {away}")
        except Exception as e:
            console.print(f"  [red]✗[/red] Failed to create {home} vs {away}: {e}")

    return matches


async def demo_create_predictions(
    prediction_service: PredictionService,
    users: list,
    matches: list,
) -> None:
    """Create demo predictions."""
    console.print("\n[bold cyan]Creating demo predictions...[/bold cyan]")

    import random

    for user in users:
        for match in matches[:3]:  # Predict first 3 matches
            try:
                home_score = random.randint(0, 4)
                away_score = random.randint(0, 3)

                await prediction_service.create_prediction(
                    user_id=user.id,
                    match_id=match.id,
                    home_score=home_score,
                    away_score=away_score,
                )
                console.print(
                    f"  [green]✓[/green] {user.username} predicted "
                    f"{match.home_team} {home_score}-{away_score} {match.away_team}"
                )
            except Exception as e:
                console.print(f"  [yellow]○[/yellow] Prediction exists or failed: {e}")


async def demo_finish_match(
    match_service: MatchService,
    matches: list,
) -> None:
    """Finish a match and score predictions."""
    if not matches:
        return

    console.print("\n[bold cyan]Finishing first match...[/bold cyan]")

    match = matches[0]

    try:
        # First start the match
        await match_service.start_match(match.id)
        console.print(f"  [green]✓[/green] Started match: {match.home_team} vs {match.away_team}")

        # Then finish it with a result
        result = MatchResult(home_score=2, away_score=1)
        updated_match, scored_count = await match_service.finish_match(
            match.id,
            result,
            score_predictions=True,
        )

        console.print(
            f"  [green]✓[/green] Finished match: {updated_match.home_team} "
            f"{updated_match.home_score}-{updated_match.away_score} {updated_match.away_team}"
        )
        console.print(f"  [green]✓[/green] Scored {scored_count} predictions")
    except Exception as e:
        console.print(f"  [red]✗[/red] Failed to finish match: {e}")


async def demo_show_leaderboard(analytics_service: AnalyticsService) -> None:
    """Display the leaderboard."""
    console.print("\n[bold cyan]Leaderboard:[/bold cyan]")

    try:
        from src.models.analytics import LeaderboardType, TimePeriod

        leaderboard = await analytics_service.get_leaderboard(
            leaderboard_type=LeaderboardType.POINTS,
            period=TimePeriod.ALL_TIME,
            limit=10,
            min_predictions=1,
        )

        table = Table(title="🏆 Predictions Leaderboard")
        table.add_column("Rank", justify="center", style="cyan")
        table.add_column("User", style="green")
        table.add_column("Points", justify="right", style="yellow")
        table.add_column("Predictions", justify="right")
        table.add_column("Accuracy", justify="right", style="magenta")

        for entry in leaderboard.entries:
            table.add_row(
                f"#{entry.rank}",
                entry.username,
                str(entry.total_points),
                str(entry.total_predictions),
                f"{entry.accuracy_percent}%",
            )

        console.print(table)
    except Exception as e:
        console.print(f"  [red]✗[/red] Failed to get leaderboard: {e}")


async def demo_show_stats(analytics_service: AnalyticsService) -> None:
    """Display system statistics."""
    console.print("\n[bold cyan]System Statistics:[/bold cyan]")

    try:
        stats = await analytics_service.get_system_stats()

        table = Table(title="📊 System Stats")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right", style="green")

        table.add_row("Total Users", str(stats.total_users))
        table.add_row("Active Users", str(stats.active_users))
        table.add_row("Total Matches", str(stats.total_matches))
        table.add_row("Finished Matches", str(stats.finished_matches))
        table.add_row("Pending Matches", str(stats.pending_matches))
        table.add_row("Total Predictions", str(stats.total_predictions))
        table.add_row("Scored Predictions", str(stats.scored_predictions))
        table.add_row("Avg Predictions/Match", f"{stats.avg_predictions_per_match:.2f}")
        table.add_row("Global Accuracy", f"{stats.global_accuracy_percent}%")

        console.print(table)
    except Exception as e:
        console.print(f"  [red]✗[/red] Failed to get stats: {e}")


async def run_demo() -> None:
    """Run a complete demo of the predictions system."""
    console.print(
        Panel.fit(
            "[bold blue]Match Predictions System Demo[/bold blue]\nMongoDB + Motor + Pydantic",
            border_style="blue",
        )
    )

    settings = get_settings()
    console.print(f"\n[dim]Environment: {settings.app.environment}[/dim]")

    # Check connection
    if not await check_connection():
        console.print("\n[red]Cannot proceed without database connection.[/red]")
        console.print("Make sure MongoDB is running:")
        console.print("  cd docker && docker-compose up -d")
        return

    # Setup indexes
    await setup_indexes()

    # Get database and initialize services
    db = await get_database()

    user_service = UserService(db)
    match_service = MatchService(db)
    prediction_service = PredictionService(db)
    analytics_service = AnalyticsService(db)

    # Run demo steps
    users = await demo_create_users(user_service)
    matches = await demo_create_matches(match_service)

    if users and matches:
        await demo_create_predictions(prediction_service, users, matches)
        await demo_finish_match(match_service, matches)

    # Show results
    await demo_show_leaderboard(analytics_service)
    await demo_show_stats(analytics_service)

    # Cleanup
    await close_database()

    console.print("\n[green]Demo completed![/green]")


async def main() -> None:
    """Main entry point."""
    try:
        await run_demo()
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
    except Exception as e:
        logger.exception("Application error")
        console.print(f"\n[red]Error: {e}[/red]")
        sys.exit(1)
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())

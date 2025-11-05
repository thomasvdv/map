"""CLI interface for OLC Downloader"""

import click
import logging
from pathlib import Path
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # dotenv not installed, skip
    pass

from .config import Config
from .auth import OLCAuthenticator
from .scraper_scrapy import OLCScraperScrapy as OLCScraper
from .downloader import DownloadManager
from .map_generator import MapGenerator
from .exceptions import OLCDownloaderError, AuthenticationError, ConfigurationError, RateLimitError

console = Console()


def setup_logging(verbose: bool = False):
    """Setup logging with Rich handler"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)]
    )


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """OLC Downloader - Download your IGC files from onlinecontest.org"""
    pass


@cli.command()
@click.option('--username', '-u', prompt=True, help='OLC username')
@click.option('--password', '-p', prompt=True, hide_input=True, help='OLC password')
def configure(username: str, password: str):
    """Configure OLC credentials"""
    try:
        config = Config()
        config.save_credentials(username, password)
        console.print(f"[green]✓[/] Credentials saved to {config.config_file}")
    except Exception as e:
        console.print(f"[red]✗[/] Error: {e}", style="bold red")
        raise click.Abort()


@cli.command()
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def list_years(verbose: bool):
    """List available years with flights"""
    setup_logging(verbose)

    try:
        config = Config()
        username, password = config.get_credentials()

        console.print("[cyan]Logging in to OLC...[/]")
        auth = OLCAuthenticator()
        auth.login(username, password)

        console.print("[cyan]Fetching available years...[/]")
        scraper = OLCScraper(auth.get_session())
        years = scraper.get_available_years()

        if not years:
            console.print("[yellow]No years found[/]")
            return

        # Create table
        table = Table(title="Available Years")
        table.add_column("Year", style="cyan", justify="center")

        for year in years:
            table.add_row(year)

        console.print(table)

    except ConfigurationError as e:
        console.print(f"[red]Configuration Error:[/] {e}")
        console.print("\n[yellow]Tip:[/] Run 'olc-download configure' to set up credentials")
        raise click.Abort()
    except AuthenticationError as e:
        console.print(f"[red]Authentication Error:[/] {e}")
        raise click.Abort()
    except OLCDownloaderError as e:
        console.print(f"[red]Error:[/] {e}", style="bold red")
        raise click.Abort()


@cli.command()
@click.option('--year', '-y', help='Download only specific year')
@click.option('--output', '-o', type=click.Path(), help='Output directory (default: ./downloads)')
@click.option('--force', '-f', is_flag=True, help='Re-download existing files')
@click.option('--dry-run', '-n', is_flag=True, help='Show what would be downloaded without downloading')
@click.option('--retries', '-r', type=int, default=3, help='Number of retry attempts for failed downloads (default: 3)')
@click.option('--airport', '-a', help='Filter by airport name (exact match, case-insensitive) - for YOUR flights only')
@click.option('--airport-code', help='OLC airport code (e.g., STAUB1) - downloads ALL pilots\' flights from this airport. Requires --all-pilots flag')
@click.option('--all-pilots', is_flag=True, help='Download public flights from ALL pilots (requires --airport-code)')
@click.option('--min-points', '-p', type=float, help='Filter by minimum points score')
@click.option('--generate-map', '-m', is_flag=True, help='Automatically generate map after downloading (requires --airport-code)')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def download(year: str, output: str, force: bool, dry_run: bool, retries: int, airport: str, airport_code: str, all_pilots: bool, min_points: float, generate_map: bool, verbose: bool):
    """Download IGC files from OLC"""
    setup_logging(verbose)

    try:
        # Validate options
        if all_pilots and not airport_code:
            console.print("[red]Error:[/] --all-pilots requires --airport-code")
            raise click.Abort()

        if airport_code and not all_pilots:
            console.print("[red]Error:[/] --airport-code requires --all-pilots flag")
            raise click.Abort()

        if all_pilots and airport:
            console.print("[red]Error:[/] Cannot use both --all-pilots and --airport. Use --airport-code with --all-pilots for public flights.")
            raise click.Abort()

        config = Config()
        username, password = config.get_credentials()
        output_dir = config.get_download_dir(output)

        console.print("[cyan]Logging in to OLC...[/]")
        auth = OLCAuthenticator()
        auth.login(username, password)

        scraper = OLCScraper(auth.get_session())

        if all_pilots:
            # Public flight mode - scrape all pilots' flights from specific airport
            console.print(f"[cyan]Discovering PUBLIC flights from all pilots at airport {airport_code}...[/]")
            console.print("[yellow]Note: Using Scrapy + Playwright to render JavaScript. Each year may take 1-2 minutes.[/]")
            console.print("[yellow]Processing most recent years first for faster results![/]")

            if min_points:
                console.print(f"[yellow]Filtering: min_points>={min_points}[/]")

            # Use incremental processing - download each year as it's scraped
            downloader = DownloadManager(auth.get_session(), output_dir, max_retries=retries, auth=auth)
            total_stats = {'total': 0, 'downloaded': 0, 'skipped': 0, 'failed': 0}

            try:
                for year_val, flights in scraper.get_public_flights_by_airport_incremental(
                    airport_code=airport_code,
                    year=year,
                    min_points=min_points,
                    output_dir=str(output_dir)
                ):
                    console.print(f"\n[cyan]Downloading {len(flights)} flights from {year_val}...[/]")

                    # Download this year's flights immediately
                    year_stats = downloader.download_flights(
                        {year_val: flights},
                        force=force,
                        dry_run=dry_run,
                        airport_code=airport_code
                    )

                    # Accumulate stats
                    for key in total_stats:
                        total_stats[key] += year_stats.get(key, 0)
            except RateLimitError:
                # Rate limit hit - exit gracefully
                raise click.Abort()

            if total_stats['total'] == 0:
                console.print("[yellow]No flights found[/]")
                return

            # Print final summary
            if not dry_run:
                console.print("\n[bold green]Overall Download Summary:[/]")
                console.print(f"  Total files: {total_stats['total']}")
                console.print(f"  Downloaded: {total_stats['downloaded']}")
                console.print(f"  Skipped (already exist): {total_stats['skipped']}")
                console.print(f"  Failed: {total_stats['failed']}")
                console.print(f"\n[green]✓[/] Files saved to: {output_dir.absolute()}")

            return  # Early return since we already handled everything
        else:
            # Personal flight mode - your flights only
            console.print("[cyan]Discovering flights...[/]")
            console.print("[yellow]Note: Using Scrapy + Playwright to render JavaScript. Each year may take 1-2 minutes.[/]")
            console.print("[yellow]Processing most recent years first for faster results![/]")

            # Show filter info if filters are applied
            if airport or min_points:
                filters = []
                if airport:
                    filters.append(f"airport='{airport}'")
                if min_points:
                    filters.append(f"min_points>={min_points}")
                console.print(f"[yellow]Filtering: {', '.join(filters)}[/]")

            # Use incremental processing
            downloader = DownloadManager(auth.get_session(), output_dir, max_retries=retries, auth=auth)
            total_stats = {'total': 0, 'downloaded': 0, 'skipped': 0, 'failed': 0}

            try:
                if year:
                    # Single year - scrape and download
                    flights = scraper.get_flights_for_year(year, airport=airport, min_points=min_points)
                    if flights:
                        console.print(f"\n[cyan]Downloading {len(flights)} flights from {year}...[/]")
                        year_stats = downloader.download_flights(
                            {year: flights},
                            force=force,
                            dry_run=dry_run,
                            airport_code=airport_code
                        )
                        for key in total_stats:
                            total_stats[key] += year_stats.get(key, 0)
                else:
                    # All years - incremental processing
                    for year_val, flights in scraper.get_all_flights_incremental(airport=airport, min_points=min_points):
                        console.print(f"\n[cyan]Downloading {len(flights)} flights from {year_val}...[/]")

                        # Download this year's flights immediately
                        year_stats = downloader.download_flights(
                            {year_val: flights},
                            force=force,
                            dry_run=dry_run,
                            airport_code=airport_code
                        )

                        # Accumulate stats
                        for key in total_stats:
                            total_stats[key] += year_stats.get(key, 0)
            except RateLimitError:
                # Rate limit hit - exit gracefully
                raise click.Abort()

            if total_stats['total'] == 0:
                console.print("[yellow]No flights found[/]")
                return

            # Print final summary
            if not dry_run:
                console.print("\n[bold green]Overall Download Summary:[/]")
                console.print(f"  Total files: {total_stats['total']}")
                console.print(f"  Downloaded: {total_stats['downloaded']}")
                console.print(f"  Skipped (already exist): {total_stats['skipped']}")
                console.print(f"  Failed: {total_stats['failed']}")
                console.print(f"\n[green]✓[/] Files saved to: {output_dir.absolute()}")

                # Generate map if requested
                if generate_map and airport_code:
                    console.print(f"\n[cyan]Generating map for airport {airport_code}...[/]")
                    try:
                        from .map_generator import MapGenerator
                        generator = MapGenerator(output_dir)
                        map_file = generator.generate_airport_map(
                            airport_code=airport_code,
                            deployment_mode='local',
                            skip_satellite_tiles=False,
                        )
                        console.print(f"[green]✓[/] Map generated: {map_file.absolute()}")
                        console.print(f"[cyan]Open in browser:[/] file://{map_file.absolute()}")
                    except Exception as e:
                        console.print(f"[yellow]Warning:[/] Failed to generate map: {e}")
                        if verbose:
                            import traceback
                            console.print(traceback.format_exc())

    except ConfigurationError as e:
        console.print(f"[red]Configuration Error:[/] {e}")
        console.print("\n[yellow]Tip:[/] Run 'olc-download configure' to set up credentials")
        raise click.Abort()
    except AuthenticationError as e:
        console.print(f"[red]Authentication Error:[/] {e}")
        raise click.Abort()
    except OLCDownloaderError as e:
        console.print(f"[red]Error:[/] {e}", style="bold red")
        raise click.Abort()


@cli.command()
@click.option('--year', '-y', help='List flights for specific year')
@click.option('--airport', '-a', help='Filter by airport name (exact match, case-insensitive) - for YOUR flights only')
@click.option('--airport-code', help='OLC airport code (e.g., STAUB1) - lists ALL pilots\' flights from this airport. Requires --all-pilots flag')
@click.option('--all-pilots', is_flag=True, help='List public flights from ALL pilots (requires --airport-code)')
@click.option('--min-points', '-p', type=float, help='Filter by minimum points score')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def list_flights(year: str, airport: str, airport_code: str, all_pilots: bool, min_points: float, verbose: bool):
    """List available flights"""
    setup_logging(verbose)

    try:
        # Validate options
        if all_pilots and not airport_code:
            console.print("[red]Error:[/] --all-pilots requires --airport-code")
            raise click.Abort()

        if airport_code and not all_pilots:
            console.print("[red]Error:[/] --airport-code requires --all-pilots flag")
            raise click.Abort()

        if all_pilots and airport:
            console.print("[red]Error:[/] Cannot use both --all-pilots and --airport. Use --airport-code with --all-pilots for public flights.")
            raise click.Abort()

        config = Config()
        username, password = config.get_credentials()

        console.print("[cyan]Logging in to OLC...[/]")
        auth = OLCAuthenticator()
        auth.login(username, password)

        scraper = OLCScraper(auth.get_session())

        if all_pilots:
            # Public flight mode
            console.print(f"[cyan]Fetching PUBLIC flights from all pilots at airport {airport_code}...[/]")

            if min_points:
                console.print(f"[yellow]Filtering: min_points>={min_points}[/]")

            flights_by_year = scraper.get_public_flights_by_airport(
                airport_code=airport_code,
                year=year,
                min_points=min_points
            )
        else:
            # Personal flight mode
            console.print("[cyan]Fetching flights...[/]")

            # Show filter info if filters are applied
            if airport or min_points:
                filters = []
                if airport:
                    filters.append(f"airport='{airport}'")
                if min_points:
                    filters.append(f"min_points>={min_points}")
                console.print(f"[yellow]Filtering: {', '.join(filters)}[/]")

            if year:
                flights_by_year = {year: scraper.get_flights_for_year(year, airport=airport, min_points=min_points)}
            else:
                flights_by_year = scraper.get_all_flights(airport=airport, min_points=min_points)

        # Create table with airport, points, and pilot columns
        table = Table(title="Available Flights" if not all_pilots else f"Public Flights at {airport_code}")
        table.add_column("Year", style="cyan")
        table.add_column("Date", style="green")
        if all_pilots:
            table.add_column("Pilot", style="bright_blue")
        table.add_column("Airport", style="magenta")
        table.add_column("Points", style="blue", justify="right")
        table.add_column("Filename", style="yellow")

        for year_val, flights in sorted(flights_by_year.items(), reverse=True):
            for flight in flights:
                row_data = [
                    flight.year,
                    flight.date,
                ]
                if all_pilots:
                    row_data.append(flight.pilot or "-")
                row_data.extend([
                    flight.airport or "-",
                    f"{flight.points:.2f}" if flight.points is not None else "-",
                    flight.filename
                ])
                table.add_row(*row_data)

        console.print(table)

        # Summary
        total = sum(len(flights) for flights in flights_by_year.values())
        console.print(f"\n[bold]Total flights: {total}[/]")

    except ConfigurationError as e:
        console.print(f"[red]Configuration Error:[/] {e}")
        console.print("\n[yellow]Tip:[/] Run 'olc-download configure' to set up credentials")
        raise click.Abort()
    except AuthenticationError as e:
        console.print(f"[red]Authentication Error:[/] {e}")
        raise click.Abort()
    except OLCDownloaderError as e:
        console.print(f"[red]Error:[/] {e}", style="bold red")
        raise click.Abort()


@cli.command()
@click.option('--airport-code', '-a', required=True, help='Airport code (e.g., STERL1)')
@click.option('--output', '-o', type=click.Path(), help='Output directory (default: ./downloads)')
@click.option('--min-points', '-p', type=float, help='Minimum points score to include flights')
@click.option('--year', '-y', help='Download only specific year')
@click.option('--skip-download', is_flag=True, help='Skip download, only generate map from existing files')
@click.option('--force', '-f', is_flag=True, help='Re-download existing files')
@click.option('--max-tracks', '-m', type=int, help='Maximum number of tracks to display (default: all)')
@click.option('--deployment-mode', '-d', type=click.Choice(['local', 'static']), default='static', help='Deployment mode: local (absolute paths) or static (relative paths for R2/CDN)')
@click.option('--skip-satellite-tiles', is_flag=True, help='Skip automatic satellite tile generation (faster, but no date-specific satellite imagery)')
@click.option('--no-upload', is_flag=True, help='Skip automatic upload to Cloudflare R2')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def map(airport_code: str, output: str, min_points: float, year: str, skip_download: bool, force: bool, max_tracks: int, deployment_mode: str, skip_satellite_tiles: bool, no_upload: bool, verbose: bool):
    """Download flights and generate interactive map for an airport (downloads all pilots by default)"""
    setup_logging(verbose)

    try:
        from .exceptions import ConfigurationError, AuthenticationError, RateLimitError

        config = Config()
        output_dir = config.get_download_dir(output)

        # Step 1: Download flights (unless skip-download is set)
        if not skip_download:
            console.print("[cyan]Logging in to OLC...[/]")
            from .auth import OLCAuthenticator
            from .scraper_scrapy import OLCScraperScrapy
            from .downloader import DownloadManager

            username, password = config.get_credentials()
            auth = OLCAuthenticator()
            auth.login(username, password)

            scraper = OLCScraperScrapy(auth.get_session())

            console.print(f"[cyan]Discovering flights from all pilots at airport {airport_code}...[/]")
            console.print("[yellow]Note: Using Scrapy + Playwright to render JavaScript. Each year may take 1-2 minutes.[/]")

            if min_points:
                console.print(f"[yellow]Filtering: min_points>={min_points}[/]")

            downloader = DownloadManager(auth.get_session(), output_dir, max_retries=3, auth=auth)
            total_stats = {'total': 0, 'downloaded': 0, 'skipped': 0, 'failed': 0}

            try:
                for year_val, flights in scraper.get_public_flights_by_airport_incremental(
                    airport_code=airport_code,
                    year=year,
                    min_points=min_points,
                    output_dir=output_dir
                ):
                    console.print(f"\n[cyan]Downloading {len(flights)} flights from {year_val}...[/]")

                    year_stats = downloader.download_flights(
                        {year_val: flights},
                        force=force,
                        dry_run=False,
                        airport_code=airport_code
                    )

                    for key in total_stats:
                        total_stats[key] += year_stats.get(key, 0)
            except RateLimitError:
                console.print("[yellow]Note: Hit download limit, will generate map with downloaded flights[/]")

            if total_stats['total'] > 0:
                console.print("\n[bold green]Download Summary:[/]")
                console.print(f"  Downloaded: {total_stats['downloaded']}")
                console.print(f"  Skipped: {total_stats['skipped']}")
                console.print(f"  Failed: {total_stats['failed']}")

        # Step 2: Generate map
        console.print(f"\n[cyan]Generating map for airport {airport_code}...[/]")
        if deployment_mode == 'static':
            console.print(f"[cyan]Using static mode (relative URLs for R2)[/]")
        if skip_satellite_tiles:
            console.print(f"[yellow]Skipping satellite tile generation[/]")
        if not no_upload:
            console.print(f"[cyan]Will upload to R2 after generation[/]")

        from .map_generator import MapGenerator
        generator = MapGenerator(output_dir)
        map_file = generator.generate_airport_map(
            airport_code=airport_code,
            max_tracks=max_tracks,
            deployment_mode=deployment_mode,
            skip_satellite_tiles=skip_satellite_tiles,
        )

        console.print(f"\n[green]✓[/] Map generated: {map_file.absolute()}")
        console.print(f"\n[cyan]Open the map in your browser:[/] file://{map_file.absolute()}")

        # Upload to R2 automatically (unless --no-upload is specified)
        if not no_upload:
            try:
                from .r2_uploader import R2Uploader
                from pathlib import Path as PathlibPath

                console.print(f"\n[cyan]Uploading to R2...[/]")
                uploader = R2Uploader()

                # Upload satellite tiles first
                sat_tiles_dir = PathlibPath('daily_sat_tiles')
                if sat_tiles_dir.exists() and not skip_satellite_tiles:
                    console.print(f"[cyan]Uploading satellite tiles...[/]")
                    uploaded, skipped, total = uploader.upload_satellite_tiles(sat_tiles_dir)
                    if uploaded > 0 or skipped > 0:
                        console.print(f"[green]✓[/] Satellite tiles: {uploaded} uploaded, {skipped} skipped, {total} total")
                    else:
                        console.print(f"[yellow]⚠[/] No satellite tiles uploaded")

                # Upload map
                console.print(f"[cyan]Uploading map...[/]")
                if uploader.upload_map(map_file):
                    console.print(f"[green]✓[/] Map uploaded to R2 successfully")
                    # index.html is at root, other maps in maps/ subdirectory
                    if map_file.name == 'index.html':
                        url = uploader.get_public_url('index.html')
                    else:
                        url = uploader.get_public_url(f"maps/{map_file.name}")
                    console.print(f"[green]Public URL:[/] {url}")
                else:
                    console.print(f"[yellow]⚠[/] Failed to upload map to R2")

            except ValueError as e:
                console.print(f"\n[yellow]⚠  R2 upload skipped:[/] {e}")
                console.print("[dim]Set R2 credentials to enable automatic uploads:[/]")
                console.print("[dim]  export R2_ACCOUNT_ID=your-account-id[/]")
                console.print("[dim]  export R2_ACCESS_KEY_ID=your-access-key-id[/]")
                console.print("[dim]  export R2_SECRET_ACCESS_KEY=your-secret-access-key[/]")
            except ImportError:
                console.print(f"\n[yellow]⚠  R2 upload skipped:[/] boto3 not installed")
                console.print("[dim]Install with: pip install boto3[/]")

    except ConfigurationError as e:
        console.print(f"[red]Configuration Error:[/] {e}")
        console.print("\n[yellow]Tip:[/] Run 'olc-download configure' to set up credentials")
        raise click.Abort()
    except AuthenticationError as e:
        console.print(f"[red]Authentication Error:[/] {e}")
        raise click.Abort()
    except ValueError as e:
        console.print(f"[red]Error:[/] {e}", style="bold red")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]Error:[/] {e}", style="bold red")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise click.Abort()


@cli.command()
@click.option('--airport-code', '-a', help='Airport code to generate tiles for (e.g., STERL1)')
@click.option('--downloads-dir', '-d', type=click.Path(), default='downloads', help='Directory containing flight downloads (default: ./downloads)')
@click.option('--output-dir', '-o', type=click.Path(), default='daily_sat_tiles', help='Output directory for satellite tiles (default: ./daily_sat_tiles)')
@click.option('--dates', multiple=True, help='Specific dates to generate (YYYY-MM-DD format, can specify multiple times)')
@click.option('--all-dates', is_flag=True, help='Generate tiles for all flight dates')
@click.option('--zoom-start', type=int, default=8, help='Start zoom level (default: 8)')
@click.option('--zoom-end', type=int, default=9, help='End zoom level (default: 9, NASA VIIRS native max)')
@click.option('--force-regenerate', is_flag=True, help='Regenerate existing tiles')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def generate_satellite_tiles(
    airport_code: str,
    downloads_dir: str,
    output_dir: str,
    dates: tuple,
    all_dates: bool,
    zoom_start: int,
    zoom_end: int,
    force_regenerate: bool,
    verbose: bool
):
    """Generate date-specific satellite tiles from NASA GIBS VIIRS imagery

    Downloads historical satellite imagery tiles for dates when flights were recorded,
    allowing pilots to review actual cloud and weather conditions from their flight days.

    Examples:
        # Generate tiles for all flight dates at Sterling airport
        olc-download generate-satellite-tiles --airport-code STERL1 --all-dates

        # Generate tiles for specific dates
        olc-download generate-satellite-tiles --dates 2024-07-27 --dates 2024-08-15

        # Generate with higher zoom levels (more storage required)
        olc-download generate-satellite-tiles --airport-code STERL1 --all-dates --zoom-end 10
    """
    setup_logging(verbose)

    try:
        from pathlib import Path
        import sys

        # Import the satellite tile manager
        from .satellite_tile_generator import SatelliteTileManager

        # Validate inputs
        if not dates and not all_dates:
            console.print("[red]Error:[/] Must specify either --dates or --all-dates")
            raise click.Abort()

        if not all_dates and not dates:
            console.print("[red]Error:[/] No dates specified")
            raise click.Abort()

        downloads_path = Path(downloads_dir)
        output_path = Path(output_dir)

        if not downloads_path.exists():
            console.print(f"[red]Error:[/] Downloads directory not found: {downloads_path}")
            raise click.Abort()

        # Initialize manager
        tile_manager = SatelliteTileManager(output_path)

        # Get dates to process
        if dates:
            dates_to_process = set(dates)
            console.print(f"[cyan]Processing {len(dates_to_process)} specified dates[/]")
        else:  # all_dates
            console.print(f"[cyan]Extracting flight dates from metadata...[/]")
            all_flight_dates = tile_manager.get_unique_flight_dates(downloads_path, airport_code)

            if not all_flight_dates:
                console.print(f"[yellow]No flight dates found in {downloads_path}[/]")
                if airport_code:
                    console.print(f"[yellow]Hint: Make sure flights for airport '{airport_code}' have been downloaded[/]")
                raise click.Abort()

            # Filter to VIIRS-available dates
            viirs_dates, pre_viirs_dates = tile_manager.filter_viirs_dates(all_flight_dates)

            if pre_viirs_dates:
                console.print(f"[yellow]Note: Skipping {len(pre_viirs_dates)} flights before 2012-01-19 (VIIRS availability)[/]")
                if verbose:
                    console.print(f"[yellow]Pre-VIIRS dates: {sorted(pre_viirs_dates)}[/]")

            if not viirs_dates:
                console.print(f"[yellow]No dates in VIIRS range (2012-01-19 onwards)[/]")
                raise click.Abort()

            dates_to_process = viirs_dates
            console.print(f"[cyan]Found {len(dates_to_process)} unique flight dates with VIIRS coverage[/]")

        # Check which dates already have tiles
        if not force_regenerate:
            existing_dates = tile_manager.get_generated_dates()
            new_dates = dates_to_process - existing_dates
            skipped_count = len(dates_to_process) - len(new_dates)

            if skipped_count > 0:
                console.print(f"[yellow]Skipping {skipped_count} dates with existing tiles (use --force-regenerate to regenerate)[/]")

            dates_to_process = new_dates

        if not dates_to_process:
            console.print(f"[green]All tiles already exist![/]")
            return

        console.print(f"[cyan]Will generate tiles for {len(dates_to_process)} dates: {sorted(dates_to_process)}[/]")
        console.print(f"[cyan]Zoom levels: {zoom_start} to {zoom_end}[/]")
        console.print(f"[yellow]Note: VIIRS native resolution is z0-9. Higher zooms use client-side upscaling.[/]")

        # Import and run the tile fetching logic
        # We'll call the script as a subprocess for now
        import subprocess

        script_path = Path(__file__).parent.parent.parent / 'tile_generator' / 'scripts' / 'fetch_nasa_tiles.py'

        if not script_path.exists():
            console.print(f"[red]Error:[/] Tile fetcher script not found: {script_path}")
            raise click.Abort()

        # Build command
        cmd = [
            sys.executable,
            str(script_path),
            '--downloads-dir', str(downloads_path),
            '--output-dir', str(output_path),
            '--zoom-start', str(zoom_start),
            '--zoom-end', str(zoom_end),
        ]

        if airport_code:
            cmd.extend(['--airport-code', airport_code])

        if dates:
            cmd.append('--dates')
            cmd.extend(dates)
        else:
            cmd.append('--all-dates')

        if force_regenerate:
            cmd.append('--force-regenerate')

        # Run the script
        console.print(f"\n[cyan]Starting tile generation...[/]")
        result = subprocess.run(cmd, capture_output=False)

        if result.returncode == 0:
            console.print(f"\n[green]✓[/] Satellite tiles generated successfully!")
            console.print(f"[cyan]Tiles saved to:[/] {output_path}")
            console.print(f"\n[cyan]Next steps:[/]")
            console.print(f"  1. Generate map with: olc-download map --airport-code {airport_code or 'YOUR_CODE'}")
            console.print(f"  2. Select 'Satellite (Flight Date)' layer in the map to view historical imagery")
        else:
            console.print(f"\n[red]✗[/] Tile generation failed with exit code {result.returncode}")
            raise click.Abort()

    except Exception as e:
        console.print(f"[red]Error:[/] {e}", style="bold red")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise click.Abort()


@cli.command()
@click.option('--output', '-o', type=click.Path(), help='Output directory (default: ./downloads)')
@click.option('--dry-run', '-n', is_flag=True, help='Show what would be deleted without deleting')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def cleanup(output: str, dry_run: bool, verbose: bool):
    """Remove invalid HTML files from downloads directory"""
    setup_logging(verbose)

    try:
        from pathlib import Path

        config = Config()
        output_dir = config.get_download_dir(output)

        if not output_dir.exists():
            console.print(f"[yellow]Directory not found:[/] {output_dir}")
            return

        console.print(f"[cyan]Scanning for invalid IGC files in {output_dir}...[/]")

        # Find all .igc files
        igc_files = list(output_dir.rglob('*.igc'))
        invalid_files = []

        for igc_file in igc_files:
            try:
                with open(igc_file, 'r', encoding='latin-1') as f:
                    first_line = f.readline().strip()
                    if first_line.startswith('<!DOCTYPE') or first_line.startswith('<html'):
                        invalid_files.append(igc_file)
            except:
                pass  # Skip files we can't read

        if not invalid_files:
            console.print("[green]✓[/] No invalid files found!")
            return

        console.print(f"\n[yellow]Found {len(invalid_files)} invalid HTML files:[/]")

        for invalid_file in invalid_files:
            console.print(f"  - {invalid_file.relative_to(output_dir)}")

        if dry_run:
            console.print(f"\n[cyan]Dry run - no files deleted[/]")
            console.print(f"Run without --dry-run to delete these files")
        else:
            for invalid_file in invalid_files:
                invalid_file.unlink()
            console.print(f"\n[green]✓[/] Deleted {len(invalid_files)} invalid files")
            console.print(f"\n[cyan]Tip:[/] Re-download valid IGC files with:")
            console.print(f"  olc-download download --airport-code <CODE> --all-pilots")

    except Exception as e:
        console.print(f"[red]Error:[/] {e}", style="bold red")
        raise click.Abort()


def _parse_igc_file_metadata(igc_path: Path):
    """Extract metadata from IGC file headers

    Returns:
        dict with 'date' (YYYY-MM-DD format) and 'pilot' if found
    """
    import re

    metadata = {}

    try:
        with open(igc_path, 'r', encoding='latin-1', errors='ignore') as f:
            # Read first 50 lines (headers)
            for i, line in enumerate(f):
                if i > 50:
                    break

                line = line.strip()

                # Extract date: HFDTEDATE:DDMMYY or HFDTE DDMMYY
                if line.startswith('HFDTEDATE:') or line.startswith('HFDTE'):
                    date_match = re.search(r'(\d{6})', line)
                    if date_match:
                        date_str = date_match.group(1)
                        # Parse DDMMYY
                        day = int(date_str[0:2])
                        month = int(date_str[2:4])
                        year = int(date_str[4:6])
                        # Assume 20xx for year
                        year = 2000 + year
                        metadata['date'] = f"{year:04d}-{month:02d}-{day:02d}"

                # Extract pilot name
                if line.startswith('HFPLTPILOTINCHARGE:'):
                    pilot = line.split(':', 1)[1].strip()
                    if pilot:
                        metadata['pilot'] = pilot

                # Stop at first B record (flight data)
                if line.startswith('B'):
                    break

    except Exception as e:
        logger.warning(f"Failed to parse IGC file {igc_path.name}: {e}")

    return metadata


def _parse_filename(filename: str):
    """Parse filename to extract year, pilot, and flight_id

    Filename format: YEAR_PILOT_FLIGHTID.igc
    Example: 2025_Phil_Gaisford_(US_-_R1)_-1818431339.igc

    Returns:
        dict with 'year', 'pilot', 'flight_id'
    """
    stem = filename.replace('.igc', '')
    parts = stem.split('_')

    if len(parts) < 3:
        return None

    # Year is first part
    year = parts[0]

    # Flight ID is last part (can be negative)
    flight_id = parts[-1]

    # Pilot is everything in between
    pilot = '_'.join(parts[1:-1])

    return {
        'year': year,
        'pilot': pilot,
        'flight_id': flight_id
    }


@cli.command()
@click.option('--airport-code', '-a', required=True, help='Airport code (e.g., STERL1)')
@click.option('--output-dir', '-o', type=click.Path(), default='downloads', help='Output directory')
@click.option('--min-points', '-p', type=float, default=None, help='Minimum points filter (use same value as original download)')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
@click.option('--dry-run', is_flag=True, help='Show what would be done without actually doing it')
@click.option('--from-files', is_flag=True, help='Generate metadata from IGC files directly (no web scraping)')
def regenerate_metadata(airport_code: str, output_dir: str, min_points: float, verbose: bool, dry_run: bool, from_files: bool):
    """Regenerate metadata for flights missing it"""
    setup_logging(verbose)

    try:
        output_dir = Path(output_dir)
        airport_dir = output_dir / airport_code

        if not airport_dir.exists():
            console.print(f"[red]Error:[/] Airport directory not found: {airport_dir}")
            raise click.Abort()

        console.print(f"[cyan]Analyzing flights in {airport_dir}...[/]")

        # Load existing metadata
        from .metadata import MetadataStore
        metadata_store = MetadataStore(output_dir)
        all_metadata = {}

        for year_dir in airport_dir.iterdir():
            if year_dir.is_dir() and year_dir.name.isdigit():
                year_metadata = metadata_store.load_metadata(airport_code, year_dir.name)
                all_metadata.update(year_metadata)

        # Find all IGC files
        igc_files = list(airport_dir.rglob('*.igc'))
        console.print(f"[cyan]Found {len(igc_files)} IGC files[/]")
        console.print(f"[cyan]Found {len(all_metadata)} flights with metadata[/]")

        # Find files missing metadata
        missing_metadata = []
        for igc_file in igc_files:
            filename = igc_file.name
            # Check if this filename exists in metadata
            has_metadata = any(meta.filename == filename for meta in all_metadata.values())
            if not has_metadata:
                missing_metadata.append(igc_file)

        if not missing_metadata:
            console.print("[green]✓[/] All flights have metadata!")
            return

        console.print(f"[yellow]Found {len(missing_metadata)} flights missing metadata[/]")

        if min_points:
            console.print(f"[cyan]Using minimum points filter: {min_points}[/]")
        else:
            console.print(f"[yellow]No minimum points filter specified. Will fetch all flights from the airport.[/]")
            console.print(f"[yellow]If you used --min-points during download, specify the same value here for better matching.[/]")

        if dry_run:
            console.print("\n[cyan]Files that would have metadata regenerated:[/]")
            for igc_file in missing_metadata:
                console.print(f"  - {igc_file.relative_to(output_dir)}")
            return

        # Option 1: Generate metadata from files directly (no web scraping)
        if from_files:
            console.print(f"\n[cyan]Generating metadata from IGC files directly (no web scraping)...[/]")

            from .metadata import FlightMetadata

            regenerated_count = 0
            for igc_file in missing_metadata:
                # Parse filename
                filename_data = _parse_filename(igc_file.name)
                if not filename_data:
                    console.print(f"  [red]✗[/] Could not parse filename: {igc_file.name}")
                    continue

                # Parse IGC file
                igc_data = _parse_igc_file_metadata(igc_file)

                # Get year from directory structure
                year = igc_file.parent.name

                # Create metadata with what we have
                flight_id = filename_data['flight_id']
                pilot = igc_data.get('pilot', filename_data['pilot'].replace('_', ' '))
                date = igc_data.get('date', 'unknown')

                # Use flight_id as dsid (since we don't have the real dsid)
                dsid = f"file_{flight_id}"

                # Construct download URL from flight_id
                download_url = f"https://www.onlinecontest.org/olc-3.0/gliding/download.html?flightId={flight_id}"

                metadata = FlightMetadata(
                    flight_id=flight_id,
                    dsid=dsid,
                    date=date,
                    pilot=pilot,
                    airport=airport_code,
                    points=0.0,  # Unknown
                    filename=igc_file.name,
                    download_url=download_url
                )

                metadata_store.add_flight(airport_code, year, metadata)
                regenerated_count += 1
                console.print(f"  [green]✓[/] {igc_file.name} → {pilot}, {date}")

            console.print(f"\n[green]✓[/] Generated metadata for {regenerated_count}/{len(missing_metadata)} flights")
            return

        # Option 2: Authenticate and scrape from OLC website
        config = Config()
        username, password = config.get_credentials()

        if not username or not password:
            console.print("[yellow]No credentials found. Please run 'olc-download configure' first.[/]")
            raise click.Abort()

        auth = OLCAuthenticator()
        console.print(f"[cyan]Logging in as {username}...[/]")
        auth.login(username, password)

        # Group files by year and pilot
        from collections import defaultdict
        files_by_year_pilot = defaultdict(list)

        for igc_file in missing_metadata:
            # Parse filename: YEAR_PILOT_FLIGHTID.igc
            parts = igc_file.stem.split('_')
            if len(parts) >= 3:
                year = parts[0]
                pilot = '_'.join(parts[1:-1])  # Rejoin pilot name
                files_by_year_pilot[(year, pilot)].append(igc_file)

        console.print(f"\n[cyan]Scraping public flights from {airport_code} for {len(set(year for year, _ in files_by_year_pilot.keys()))} years...[/]")

        scraper = OLCScraper(auth.get_session())
        regenerated_count = 0

        # Get all unique years
        unique_years = sorted(set(year for year, _ in files_by_year_pilot.keys()), reverse=True)

        # Scrape flights by year using the public airport method
        for year in unique_years:
            console.print(f"\n[cyan]Fetching public flights from {airport_code} for {year}...[/]")

            try:
                # Use the public flights by airport method (same as --all-pilots download)
                flights = []
                for year_val, year_flights in scraper.get_public_flights_by_airport_incremental(
                    airport_code=airport_code,
                    year=year,
                    min_points=min_points,
                    output_dir=str(output_dir)
                ):
                    flights.extend(year_flights)
                    console.print(f"  Found {len(year_flights)} flights for {year_val}")

                # Debug: show what we're working with
                if verbose:
                    console.print(f"  Total scraped flights: {len(flights)}")
                    console.print(f"  Sample flight IDs: {[str(f.flight_id) for f in flights[:5]]}")

                # Get all files for this year (from any pilot)
                year_files = [f for (y, p), files in files_by_year_pilot.items() if y == year for f in files]

                if verbose:
                    console.print(f"  Looking for {len(year_files)} files from this year")

                # Match IGC files to scraped flights by comparing filename patterns
                for igc_file in year_files:
                    flight_id_from_file = igc_file.stem.split('_')[-1]

                    # Find matching flight by flight_id
                    matched_flight = None
                    for flight in flights:
                        # Try to match by flight_id (convert both to strings and compare)
                        if flight.flight_id:
                            # Handle both positive and negative flight IDs
                            if str(flight.flight_id) == flight_id_from_file:
                                matched_flight = flight
                                break
                            # Also try comparing absolute values in case of sign differences
                            try:
                                if abs(int(flight.flight_id)) == abs(int(flight_id_from_file)):
                                    matched_flight = flight
                                    break
                            except (ValueError, TypeError):
                                pass

                    if matched_flight and matched_flight.dsid:
                        # Create metadata
                        from .metadata import FlightMetadata
                        metadata = FlightMetadata(
                            flight_id=matched_flight.flight_id or '',
                            dsid=matched_flight.dsid,
                            date=matched_flight.date,
                            pilot=matched_flight.pilot or 'Unknown',
                            airport=matched_flight.airport or airport_code,
                            points=matched_flight.points or 0.0,
                            filename=igc_file.name,
                            download_url=matched_flight.url
                        )
                        metadata_store.add_flight(airport_code, year, metadata)
                        regenerated_count += 1
                        console.print(f"  [green]✓[/] {igc_file.name}")
                    else:
                        console.print(f"  [yellow]⚠[/] Could not match {igc_file.name}")

            except Exception as e:
                console.print(f"  [red]✗[/] Error: {e}")
                continue

        console.print(f"\n[green]✓[/] Regenerated metadata for {regenerated_count}/{len(missing_metadata)} flights")

    except Exception as e:
        console.print(f"[red]Error:[/] {e}", style="bold red")
        if verbose:
            raise
        raise click.Abort()

@cli.command()
@click.option('--airport-code', '-a', required=True, help='Airport code to update')
@click.option('--output-dir', default='downloads', help='Output directory')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def update_metadata_stats(airport_code: str, output_dir: str, verbose: bool):
    """Update existing metadata with official distance and speed from OLC flight listing table

    Re-scrapes the OLC website to get the official distance and speed values for all flights.
    """
    setup_logging(verbose)

    try:
        from .metadata import MetadataStore
        from .auth import OLCAuthenticator
        from .config import Config

        output_dir = Path(output_dir)
        airport_dir = output_dir / airport_code

        if not airport_dir.exists():
            console.print(f"[red]Error:[/] Airport directory not found: {airport_dir}")
            raise click.Abort()

        # Setup authentication
        config = Config()
        auth = OLCAuthenticator()

        try:
            username, password = config.get_credentials()
            auth.login(username, password)
        except Exception as e:
            console.print(f"[yellow]Warning:[/] Authentication failed: {e}")
            console.print(f"[yellow]Continuing without authentication - only public flights will be accessible[/]")

        console.print(f"[cyan]Updating metadata stats for {airport_code}...[/]")
        console.print(f"[cyan]Re-scraping OLC website to get official distance/speed values[/]")

        metadata_store = MetadataStore(output_dir)
        scraper = OLCScraper(auth.get_session())

        updated_count = 0
        total_count = 0
        missing_count = 0

        # Process each year directory that has metadata
        for year_dir in sorted(airport_dir.iterdir()):
            if not year_dir.is_dir() or not year_dir.name.isdigit():
                continue

            # Check if this year has metadata (i.e., downloaded flights)
            metadata_file = year_dir / "metadata.json"
            if not metadata_file.exists():
                continue

            year = year_dir.name
            console.print(f"\n[cyan]Processing year {year}...[/]")
            console.print(f"[cyan]Scraping OLC flight listing for {airport_code} {year}...[/]")

            # Scrape OLC website for this airport/year to get official stats
            try:
                flights_by_year = scraper.get_public_flights_by_airport(
                    airport_code=airport_code,
                    year=year,
                    min_points=None
                )
                scraped_flights = flights_by_year.get(year, [])
            except Exception as e:
                console.print(f"  [red]✗[/] Failed to scrape OLC for {year}: {e}")
                continue

            # Build a lookup dict of scraped data by dsid
            scraped_lookup = {}
            for flight in scraped_flights:
                if flight.dsid:
                    scraped_lookup[flight.dsid] = {
                        'distance': flight.distance,
                        'speed': flight.speed,
                    }

            console.print(f"  Scraped {len(scraped_lookup)} flights from OLC")

            # Load existing metadata
            year_metadata = metadata_store.load_metadata(airport_code, year)
            if not year_metadata:
                console.print(f"  No metadata found for {year}")
                continue

            total_count += len(year_metadata)
            updated_flights = []

            for dsid, flight_meta in year_metadata.items():
                # Try to find matching scraped data
                if dsid in scraped_lookup:
                    olc_data = scraped_lookup[dsid]
                    flight_meta.distance = olc_data['distance']
                    flight_meta.speed = olc_data['speed']
                    updated_count += 1

                    if olc_data['distance'] and olc_data['speed']:
                        console.print(f"  [green]✓[/] {flight_meta.filename}: {olc_data['distance']:.1f} km, {olc_data['speed']:.1f} km/h")
                    else:
                        console.print(f"  [yellow]![/] {flight_meta.filename}: No distance/speed in OLC data")
                else:
                    missing_count += 1
                    console.print(f"  [yellow]![/] {flight_meta.filename}: Not found in OLC listing (dsid={dsid})")

                updated_flights.append(flight_meta)

            # Save updated metadata for this year
            metadata_store.save_metadata(airport_code, year, updated_flights)

        console.print(f"\n[green]✓[/] Updated {updated_count}/{total_count} flights with official OLC distance and speed")
        if missing_count > 0:
            console.print(f"[yellow]![/] {missing_count} flights not found in OLC listing (may be deleted or private)")

    except Exception as e:
        console.print(f"[red]Error:[/] {e}", style="bold red")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise click.Abort()


@cli.command()
@click.option('--vfr-tiles', is_flag=True, help='Upload VFR sectional tiles')
@click.option('--satellite-tiles', is_flag=True, help='Upload satellite tiles')
@click.option('--map', '-m', 'map_file', type=click.Path(exists=True), help='Upload specific map file')
@click.option('--all', '-a', 'upload_all', is_flag=True, help='Upload all content (VFR tiles, satellite tiles, maps)')
@click.option('--bucket', default='map', help='R2 bucket name (default: map)')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def upload_to_r2(vfr_tiles: bool, satellite_tiles: bool, map_file: str, upload_all: bool, bucket: str, verbose: bool):
    """Upload content to Cloudflare R2 storage

    This command uploads VFR tiles, satellite tiles, and/or maps to Cloudflare R2.

    Required environment variables:
      - R2_ACCOUNT_ID: Your Cloudflare account ID
      - R2_ACCESS_KEY_ID: Your R2 access key ID
      - R2_SECRET_ACCESS_KEY: Your R2 secret access key

    Examples:
        # Upload VFR tiles only
        olc-download upload-to-r2 --vfr-tiles

        # Upload satellite tiles only
        olc-download upload-to-r2 --satellite-tiles

        # Upload a specific map
        olc-download upload-to-r2 --map downloads/STERL1_map.html

        # Upload everything
        olc-download upload-to-r2 --all
    """
    setup_logging(verbose)

    try:
        from pathlib import Path
        from .r2_uploader import R2Uploader

        # Check if at least one upload type is specified
        if not (vfr_tiles or satellite_tiles or map_file or upload_all):
            console.print("[red]Error:[/] Must specify at least one upload type")
            console.print("[cyan]Use --vfr-tiles, --satellite-tiles, --map, or --all[/]")
            raise click.Abort()

        # Initialize uploader
        try:
            uploader = R2Uploader(bucket=bucket)
        except ValueError as e:
            console.print(f"[red]Configuration Error:[/] {e}")
            console.print("\n[cyan]Set these environment variables:[/]")
            console.print("  export R2_ACCOUNT_ID=your-account-id")
            console.print("  export R2_ACCESS_KEY_ID=your-access-key-id")
            console.print("  export R2_SECRET_ACCESS_KEY=your-secret-access-key")
            raise click.Abort()

        console.print(f"[cyan]Connected to R2 bucket:[/] {bucket}")
        console.print("")

        # Upload VFR tiles
        if upload_all or vfr_tiles:
            vfr_tiles_dir = Path('vfr_tiles')
            if vfr_tiles_dir.exists():
                console.print("[cyan]Uploading VFR sectional tiles...[/]")
                uploaded, skipped, total = uploader.upload_vfr_tiles(vfr_tiles_dir)
                console.print(f"[green]✓[/] VFR tiles: {uploaded} uploaded, {skipped} skipped, {total} total")
            else:
                console.print(f"[yellow]Warning:[/] VFR tiles directory not found: {vfr_tiles_dir}")

        # Upload satellite tiles
        if upload_all or satellite_tiles:
            sat_tiles_dir = Path('daily_sat_tiles')
            if sat_tiles_dir.exists():
                console.print("\n[cyan]Uploading satellite tiles...[/]")
                uploaded, skipped, total = uploader.upload_satellite_tiles(sat_tiles_dir)
                console.print(f"[green]✓[/] Satellite tiles: {uploaded} uploaded, {skipped} skipped, {total} total")
            else:
                console.print(f"[yellow]Warning:[/] Satellite tiles directory not found: {sat_tiles_dir}")

        # Upload specific map
        if map_file:
            map_path = Path(map_file)
            console.print(f"\n[cyan]Uploading map:[/] {map_path.name}")
            if uploader.upload_map(map_path):
                console.print(f"[green]✓[/] Map uploaded successfully")
                url = uploader.get_public_url(f"maps/{map_path.name}")
                console.print(f"[cyan]Public URL:[/] {url}")
            else:
                console.print(f"[red]✗[/] Failed to upload map")

        # Upload all maps if --all
        if upload_all:
            downloads_dir = Path('downloads')
            maps = list(downloads_dir.glob('*_map.html'))
            if maps:
                console.print(f"\n[cyan]Uploading {len(maps)} maps...[/]")
                for map_path in maps:
                    if uploader.upload_map(map_path):
                        console.print(f"  [green]✓[/] {map_path.name}")
                    else:
                        console.print(f"  [red]✗[/] {map_path.name}")

        console.print("\n[green]✓ Upload complete![/]")

    except ImportError as e:
        console.print(f"[red]Error:[/] Missing required package: {e}")
        console.print("[cyan]Install with:[/] pip install boto3")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]Error:[/] {e}", style="bold red")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise click.Abort()


@cli.command()
@click.option('--airport-code', required=True, help='OLC airport code (e.g., STERL1)')
@click.option('--year', '-y', help='Update metadata for specific year only')
@click.option('--output', '-o', type=click.Path(), help='Output directory (default: ./downloads)')
@click.option('--verbose', '-v', is_flag=True, help='Verbose output')
def update_metadata(airport_code: str, year: str, output: str, verbose: bool):
    """Update flight metadata from OLC without downloading IGC files

    This command scrapes the public flight listing pages to update metadata
    (distance, speed, aircraft, pilot, etc.) without downloading IGC files.
    This avoids the daily download limit while keeping metadata up-to-date.

    Examples:
        # Update all STERL1 flight metadata
        olc-download update-metadata --airport-code STERL1

        # Update only 2025 metadata
        olc-download update-metadata --airport-code STERL1 --year 2025
    """
    setup_logging(verbose)

    try:
        import requests
        import json
        from .metadata import MetadataStore, FlightMetadata

        config = Config()
        username, password = config.get_credentials()
        output_dir = config.get_download_dir(output)

        console.print("[cyan]Logging in to OLC...[/]")
        auth = OLCAuthenticator()
        auth.login(username, password)

        console.print(f"[cyan]Fetching flight metadata for airport {airport_code}...[/]")
        console.print("[yellow]Note: This only updates metadata, no IGC files will be downloaded[/]")

        metadata_store = MetadataStore(output_dir)

        # Determine years to process
        if year:
            years = [year]
        else:
            scraper = OLCScraper(auth.get_session())
            years = scraper.get_available_years()

        total_flights = 0

        for year_val in years:
            try:
                console.print(f"\n[cyan]Processing year {year_val}...[/]")

                # Use JSON API directly to get flight data
                url = f"https://www.onlinecontest.org/olc-3.0/gliding/flightsOfAirfield.html?aa={airport_code}&st=olcp&rt=olc&c=C0&sc=&sp={year_val}"

                flights = []
                offset = 0

                while True:
                    # Fetch batch using POST with JSON body
                    headers = {
                        'Accept': 'application/json',
                        'Content-Type': 'application/json',
                        'Origin': 'https://www.onlinecontest.org',
                        'Referer': url,
                    }
                    body = json.dumps({"q": "ds", "offset": offset})

                    response = auth.get_session().post(url, headers=headers, data=body, timeout=60)
                    response.raise_for_status()

                    data = response.json()

                    if verbose:
                        console.print(f"[dim]API Response keys: {list(data.keys())}[/dim]")
                        total_count = data.get('count') or data.get('total', 0)
                        if total_count:
                            console.print(f"[dim]Total records: {total_count}[/dim]")

                    # API uses 'result' key, not 'rows'
                    rows = data.get('result', data.get('rows', []))

                    if not rows:
                        break

                    for idx, row in enumerate(rows):
                        # Debug: Show first row structure
                        if verbose and idx == 0:
                            console.print(f"[dim]First row keys: {list(row.keys())}[/dim]")
                            console.print(f"[dim]Sample values: distance={row.get('distance')}, speed={row.get('speed')}, plane={row.get('plane')}[/dim]")

                        # Extract dsid - API uses 'id' field
                        dsid = row.get('id')
                        if not dsid:
                            continue
                        dsid = str(dsid)

                        # Extract pilot name - API returns nested object like {"firstName": "John", "surName": "Doe"}
                        pilot_obj = row.get('pilot', {})
                        if isinstance(pilot_obj, dict):
                            first_name = pilot_obj.get('firstName', '')
                            sur_name = pilot_obj.get('surName', '')
                            pilot = f"{first_name} {sur_name}".strip() or 'Unknown'
                        else:
                            pilot = str(pilot_obj) if pilot_obj else 'Unknown'

                        # Extract date - API uses 'date' field (string like '2024-09-14')
                        date_str = row.get('date', '')

                        # Extract distance (in km) - API uses 'distanceInKm'
                        distance_value = row.get('distanceInKm')
                        distance = None
                        if distance_value is not None:
                            try:
                                distance = float(distance_value)
                            except (ValueError, TypeError):
                                pass

                        # Extract speed (in km/h) - API uses 'speedInKmH'
                        speed_value = row.get('speedInKmH')
                        speed = None
                        if speed_value is not None:
                            try:
                                speed = float(speed_value)
                            except (ValueError, TypeError):
                                pass

                        # Extract aircraft - API uses 'airplane' field
                        aircraft_value = row.get('airplane')
                        aircraft = None
                        if aircraft_value is not None:
                            aircraft = str(aircraft_value).strip() if aircraft_value else None

                        # Extract points
                        points_value = row.get('points')
                        points = 0.0
                        if points_value is not None:
                            try:
                                points = float(points_value)
                            except (ValueError, TypeError):
                                pass

                        # Create safe filename
                        safe_pilot = pilot.replace(' ', '_').replace('/', '_')
                        filename = f"{year_val}_{safe_pilot}_{dsid}.igc"

                        # Create metadata entry
                        metadata = FlightMetadata(
                            flight_id='',  # Not available without visiting flight detail page
                            dsid=dsid,
                            date=date_str,
                            pilot=pilot,
                            airport=airport_code,
                            points=points,
                            filename=filename,
                            download_url='',  # Not available without visiting flight detail page
                            distance=distance,
                            speed=speed,
                            aircraft=aircraft
                        )

                        flights.append(metadata)

                    offset += len(rows)

                    # Check if we've got all rows
                    total_count = data.get('count', data.get('total', 0))
                    if verbose:
                        console.print(f"[dim]Processed {offset}/{total_count} flights[/dim]")
                    if offset >= total_count:
                        break

                if flights:
                    # Save metadata
                    metadata_store.save_metadata(airport_code, year_val, flights)
                    console.print(f"[green]✓[/] Updated metadata for {len(flights)} flights in {year_val}")
                    total_flights += len(flights)
                else:
                    console.print(f"[yellow]No flights found for {year_val}[/]")

            except Exception as e:
                console.print(f"[red]Error processing year {year_val}:[/] {e}")
                if verbose:
                    import traceback
                    console.print(traceback.format_exc())
                continue

        console.print(f"\n[bold green]✓ Updated metadata for {total_flights} flights total[/]")
        console.print(f"[cyan]Metadata saved to: {output_dir.absolute()}[/]")

    except ConfigurationError as e:
        console.print(f"[red]Configuration Error:[/] {e}")
        console.print("\n[yellow]Tip:[/] Run 'olc-download configure' to set up credentials")
        raise click.Abort()
    except AuthenticationError as e:
        console.print(f"[red]Authentication Error:[/] {e}")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]Error:[/] {e}", style="bold red")
        if verbose:
            import traceback
            console.print(traceback.format_exc())
        raise click.Abort()


def main():
    """Entry point for CLI"""
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]Cancelled by user[/]")
        raise click.Abort()


if __name__ == '__main__':
    main()

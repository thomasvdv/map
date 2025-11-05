"""Download manager with progress tracking"""

import requests
from pathlib import Path
from typing import List, Dict, Optional
import logging
import time
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    DownloadColumn,
    TransferSpeedColumn,
    TimeRemainingColumn,
)
from rich.console import Console
from .scraper_scrapy import IGCFlight
from .exceptions import DownloadError, RateLimitError
from .metadata import MetadataStore, FlightMetadata

logger = logging.getLogger(__name__)
console = Console()


class DownloadManager:
    """Manages downloading of IGC files with progress tracking"""

    def __init__(self, session: requests.Session, output_dir: Path, max_retries: int = 3, auth=None):
        self.session = session
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_retries = max_retries
        self.metadata_store = MetadataStore(self.output_dir)
        self.auth = auth  # Optional authenticator for session refresh

    def download_flights(
        self,
        flights_by_year: Dict[str, List[IGCFlight]],
        force: bool = False,
        dry_run: bool = False,
        airport_code: Optional[str] = None,
    ) -> Dict[str, int]:
        """
        Download all flights organized by year

        Args:
            flights_by_year: Dictionary mapping year to list of flights
            force: Re-download existing files
            dry_run: Don't actually download, just show what would be downloaded
            airport_code: If provided, files will be organized as airport_code/year/filename.igc

        Returns:
            Dictionary with download statistics
        """
        stats = {
            'total': 0,
            'downloaded': 0,
            'skipped': 0,
            'failed': 0,
        }

        # Calculate total files
        for flights in flights_by_year.values():
            stats['total'] += len(flights)

        if dry_run:
            console.print(f"[bold cyan]DRY RUN: Would download {stats['total']} files[/]")
            for year, flights in sorted(flights_by_year.items(), reverse=True):
                console.print(f"  {year}: {len(flights)} files")
            return stats

        # Create progress bar
        with Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        ) as progress:

            overall_task = progress.add_task(
                "[cyan]Downloading all flights...",
                total=stats['total']
            )

            for year, flights in sorted(flights_by_year.items(), reverse=True):
                # Create directory structure: airport_code/year or just year
                if airport_code:
                    year_dir = self.output_dir / airport_code / year
                else:
                    year_dir = self.output_dir / year
                year_dir.mkdir(parents=True, exist_ok=True)

                year_task = progress.add_task(
                    f"[green]Year {year}",
                    total=len(flights)
                )

                for flight in flights:
                    # Determine output path
                    output_file = year_dir / flight.filename

                    # Check if file is an HTML error page and delete it
                    if output_file.exists():
                        try:
                            with open(output_file, 'r', encoding='latin-1') as f:
                                first_line = f.readline().strip()
                                if first_line.startswith('<!DOCTYPE') or first_line.startswith('<html'):
                                    logger.info(f"Deleting invalid HTML file: {output_file.name}")
                                    output_file.unlink()
                        except:
                            pass  # If we can't read it, leave it alone

                    # Check if file already exists
                    if output_file.exists() and not force:
                        logger.debug(f"Skipping existing file: {output_file}")
                        stats['skipped'] += 1
                        progress.update(year_task, advance=1)
                        progress.update(overall_task, advance=1)
                        continue

                    # Download file
                    try:
                        self._download_file(flight.url, output_file, progress, year_task, referer=flight.referer)
                        stats['downloaded'] += 1
                        logger.info(f"Downloaded: {output_file}")

                        # Save metadata for this flight
                        if flight.dsid:
                            metadata = FlightMetadata(
                                flight_id=flight.flight_id or '',
                                dsid=flight.dsid,
                                date=flight.date,
                                pilot=flight.pilot or 'Unknown',
                                airport=flight.airport or 'Unknown',
                                points=flight.points or 0.0,
                                filename=flight.filename,
                                download_url=flight.url,
                                distance=flight.distance,  # From OLC listing table
                                speed=flight.speed,  # From OLC listing table
                                aircraft=flight.aircraft,  # From OLC listing table
                            )
                            self.metadata_store.add_flight(airport_code, year, metadata)

                        # Wait between downloads to be gentle on the server
                        import time
                        time.sleep(3)
                    except RateLimitError as e:
                        # Daily download limit reached - stop downloading and exit
                        console.print(f"\n[bold red]⚠️  DOWNLOAD LIMIT REACHED[/]")
                        console.print(f"[yellow]{e}[/]")
                        console.print(f"[yellow]Downloaded {stats['downloaded']} files before hitting the limit.[/]")
                        console.print(f"[yellow]You can resume downloading tomorrow - already downloaded files will be skipped.[/]")
                        # Re-raise to propagate up and exit the program
                        raise
                    except Exception as e:
                        logger.error(f"Failed to download {flight.url}: {e}")
                        stats['failed'] += 1

                        # Wait even longer after a failure
                        import time
                        time.sleep(5)

                    progress.update(overall_task, advance=1)

                progress.remove_task(year_task)

        # Print summary
        console.print("\n[bold green]Download Summary:[/]")
        console.print(f"  Total files: {stats['total']}")
        console.print(f"  Downloaded: {stats['downloaded']}")
        console.print(f"  Skipped (already exist): {stats['skipped']}")
        console.print(f"  Failed: {stats['failed']}")

        return stats

    def _download_file(
        self,
        url: str,
        output_path: Path,
        progress: Progress,
        task_id,
        referer: str = None,
    ):
        """Download a single file with progress tracking and retry logic"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                if attempt > 0:
                    # Exponential backoff: 2^attempt seconds (2s, 4s, 8s, etc.)
                    wait_time = 2 ** attempt
                    logger.info(f"Retry attempt {attempt + 1}/{self.max_retries} after {wait_time}s wait...")
                    time.sleep(wait_time)

                # Add browser-like headers, especially Referer which is required by OLC
                headers = {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'same-origin',
                }

                # Add referer if provided (required by OLC server)
                if referer:
                    headers['Referer'] = referer
                    logger.debug(f"Using referer: {referer}")

                # OLC server is very slow, use long timeout
                response = self.session.get(url, headers=headers, stream=True, timeout=180)
                response.raise_for_status()

                # Check if we got HTML instead of IGC file
                content_type = response.headers.get('content-type', '').lower()
                if 'text/html' in content_type:
                    # Read the HTML to check for specific error messages
                    html_content = response.text

                    # Check for rate limit message
                    if 'download limitation' in html_content.lower() or 'downloadlimit' in html_content.lower():
                        logger.error("Daily download limit reached!")
                        logger.error("The OLC server has a daily download limit that has been exceeded.")
                        raise RateLimitError("You have reached the download limitation for today! Please try again tomorrow.")

                    logger.warning(f"Received HTML instead of IGC file (attempt {attempt + 1}/{self.max_retries})")
                    logger.warning(f"Content-Type: {content_type}")
                    logger.warning("This usually means the session expired or authentication failed")

                    # Try to refresh session if we have auth
                    if self.auth and attempt < self.max_retries - 1:
                        logger.info("Attempting to refresh session...")
                        try:
                            self.auth.refresh_session()
                            self.session = self.auth.get_session()
                            logger.info("Session refreshed successfully")
                        except Exception as e:
                            logger.warning(f"Failed to refresh session: {e}")

                    raise DownloadError("Server returned HTML instead of IGC file - session may have expired")

                # Get file size if available
                file_size = int(response.headers.get('content-length', 0))

                # Write file with progress
                with open(output_path, 'wb') as f:
                    if file_size == 0:
                        # No content-length header, just download
                        f.write(response.content)
                    else:
                        # Download in chunks with progress
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                progress.update(task_id, advance=len(chunk))

                # Validate IGC file
                try:
                    self._validate_igc_file(output_path)
                except DownloadError as e:
                    # Validation failed - delete file and retry
                    logger.warning(f"Validation failed (attempt {attempt + 1}/{self.max_retries}): {e}")
                    if output_path.exists():
                        output_path.unlink()
                    last_error = e
                    # Continue to retry
                    continue

                # Success! Break out of retry loop
                if attempt > 0:
                    logger.info(f"Download succeeded on attempt {attempt + 1}")
                return

            except requests.Timeout as e:
                last_error = e
                logger.warning(f"Download timeout (attempt {attempt + 1}/{self.max_retries}): {e}")
                if output_path.exists():
                    output_path.unlink()  # Delete partial file
                # Continue to retry

            except requests.HTTPError as e:
                # Retry on server errors (5xx), but not on client errors (4xx)
                if e.response.status_code >= 500:
                    last_error = e
                    logger.warning(f"Server error {e.response.status_code} (attempt {attempt + 1}/{self.max_retries})")
                    if output_path.exists():
                        output_path.unlink()
                    # Continue to retry
                else:
                    # Client error (like 404) - don't retry
                    logger.error(f"Client error {e.response.status_code}: {e}")
                    if output_path.exists():
                        output_path.unlink()
                    raise DownloadError(f"Download failed: {e}")

            except RateLimitError as e:
                # Rate limit hit - don't retry, just abort
                if output_path.exists():
                    output_path.unlink()
                raise  # Re-raise to stop downloading

            except DownloadError as e:
                # Our custom error (HTML instead of IGC, validation failure, etc.)
                last_error = e
                logger.warning(f"Download error (attempt {attempt + 1}/{self.max_retries}): {e}")
                if output_path.exists():
                    output_path.unlink()
                # Continue to retry

            except requests.RequestException as e:
                last_error = e
                logger.warning(f"Download error (attempt {attempt + 1}/{self.max_retries}): {e}")
                if output_path.exists():
                    output_path.unlink()
                # Continue to retry

        # All retries exhausted
        if output_path.exists():
            output_path.unlink()
        raise DownloadError(f"Download failed after {self.max_retries} attempts: {last_error}")

    def _validate_igc_file(self, file_path: Path):
        """Validate IGC file format and raise error if invalid"""
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                first_line = f.readline().strip()

                # Check if it's an HTML file
                if first_line.startswith('<!DOCTYPE') or first_line.startswith('<html'):
                    raise DownloadError(f"Downloaded file is HTML, not IGC format")

                # IGC files should start with 'A' record (FR manufacturer/serial)
                # or sometimes 'H' record (header)
                if not (first_line.startswith('A') or first_line.startswith('H')):
                    raise DownloadError(f"File does not start with valid IGC header (got: {first_line[:20]})")

                logger.debug(f"Validated IGC file: {file_path.name}")
        except DownloadError:
            raise
        except Exception as e:
            raise DownloadError(f"Could not validate IGC file: {e}")

    def _calculate_igc_stats(self, igc_path: Path) -> tuple:
        """
        Parse IGC file to calculate distance and average speed

        Returns:
            tuple: (distance_km, avg_speed_kmh) or (None, None) if calculation fails
        """
        try:
            import re

            coordinates = []
            first_time = None
            last_time = None

            with open(igc_path, 'r', encoding='latin-1', errors='ignore') as f:
                for line in f:
                    line = line.strip()

                    # Parse B records (position fixes)
                    # Format: B HHMMSS DDMMmmmN DDDMMmmmE A PPPPP GGGGG
                    if line.startswith('B') and len(line) >= 35:
                        try:
                            time_str = line[1:7]  # HHMMSS
                            lat_str = line[7:15]   # DDMMmmmN/S
                            lon_str = line[15:24]  # DDDMMmmmE/W

                            # Store first and last time
                            if first_time is None:
                                first_time = time_str
                            last_time = time_str

                            # Parse latitude
                            lat_deg = int(lat_str[0:2])
                            lat_min = int(lat_str[2:4])
                            lat_min_dec = int(lat_str[4:7])
                            lat = lat_deg + (lat_min + lat_min_dec / 1000.0) / 60.0
                            if lat_str[7] == 'S':
                                lat = -lat

                            # Parse longitude
                            lon_deg = int(lon_str[0:3])
                            lon_min = int(lon_str[3:5])
                            lon_min_dec = int(lon_str[5:8])
                            lon = lon_deg + (lon_min + lon_min_dec / 1000.0) / 60.0
                            if lon_str[8] == 'W':
                                lon = -lon

                            coordinates.append((lat, lon))
                        except (ValueError, IndexError):
                            continue

            # Calculate distance
            if len(coordinates) < 2:
                return None, None

            total_distance = 0.0
            for i in range(1, len(coordinates)):
                lat1, lon1 = coordinates[i-1]
                lat2, lon2 = coordinates[i]
                total_distance += self._haversine_distance(lat1, lon1, lat2, lon2)

            # Calculate average speed from duration
            avg_speed_kmh = None
            if first_time and last_time:
                try:
                    start_h = int(first_time[0:2])
                    start_m = int(first_time[2:4])
                    start_s = int(first_time[4:6])
                    end_h = int(last_time[0:2])
                    end_m = int(last_time[2:4])
                    end_s = int(last_time[4:6])

                    start_hours = start_h + start_m / 60.0 + start_s / 3600.0
                    end_hours = end_h + end_m / 60.0 + end_s / 3600.0
                    duration_hours = end_hours - start_hours

                    # Handle flights that cross midnight
                    if duration_hours < 0:
                        duration_hours += 24

                    if duration_hours > 0:
                        avg_speed_kmh = total_distance / duration_hours
                except (ValueError, IndexError, ZeroDivisionError):
                    pass

            return total_distance, avg_speed_kmh

        except Exception as e:
            logger.warning(f"Failed to calculate stats for {igc_path.name}: {e}")
            return None, None

    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate distance between two points using Haversine formula

        Returns:
            Distance in kilometers
        """
        import math

        # Convert to radians
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)

        # Haversine formula
        a = math.sin(delta_lat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon/2)**2
        c = 2 * math.asin(math.sqrt(a))

        # Earth radius in kilometers
        earth_radius = 6371.0

        return earth_radius * c

    def download_year(
        self,
        year: str,
        flights: List[IGCFlight],
        force: bool = False,
    ) -> int:
        """
        Download flights for a specific year

        Args:
            year: Year string
            flights: List of flights to download
            force: Re-download existing files

        Returns:
            Number of files downloaded
        """
        flights_by_year = {year: flights}
        stats = self.download_flights(flights_by_year, force=force)
        return stats['downloaded']

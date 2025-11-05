"""IGC file discovery using Scrapy with Playwright for JavaScript rendering"""

import requests
from typing import List, Dict
import logging
import re
import time
from .exceptions import ScrapingError
from .scrapy_runner import ScrapyRunner

logger = logging.getLogger(__name__)


class IGCFlight:
    """Represents a single flight/IGC file"""

    def __init__(self, url: str, filename: str, date: str, year: str, flight_id: str = None, dsid: str = None, referer: str = None, airport: str = None, points: float = None, pilot: str = None, distance: float = None, speed: float = None, aircraft: str = None, **kwargs):
        self.url = url
        self.filename = filename
        self.date = date
        self.year = year
        self.flight_id = flight_id
        self.dsid = dsid  # Dataset ID (unique identifier for the flight)
        self.referer = referer  # Referer URL needed for download
        self.airport = airport  # Takeoff airport
        self.points = points  # Points score
        self.pilot = pilot  # Pilot name (for public flights)
        self.distance = distance  # Distance in km (from OLC)
        self.speed = speed  # Average speed in km/h (from OLC)
        self.aircraft = aircraft  # Aircraft type (from OLC)
        self.metadata = kwargs

    def __repr__(self):
        return f"IGCFlight(date={self.date}, filename={self.filename}, flight_id={self.flight_id}, dsid={self.dsid}, pilot={self.pilot}, airport={self.airport}, points={self.points}, distance={self.distance}, speed={self.speed}, aircraft={self.aircraft})"


class OLCScraperScrapy:
    """Scrapes IGC files from OLC website using Scrapy + Playwright"""

    BASE_URL = "https://www.onlinecontest.org"
    DOWNLOAD_URL = f"{BASE_URL}/olc-3.0/gliding/download.html"

    def __init__(self, session: requests.Session):
        self.session = session
        self.pilot_id = None

    def _get_pilot_id(self) -> str:
        """Extract pilot ID from logged-in session"""
        if self.pilot_id:
            return self.pilot_id

        try:
            logger.info("Discovering pilot ID from logged-in session...")
            response = self.session.get(f"{self.BASE_URL}/olc-3.0/gliding/index.html", timeout=10)
            response.raise_for_status()

            pilot_id_match = re.search(r'pi=(\d+)', response.text)
            if pilot_id_match:
                self.pilot_id = pilot_id_match.group(1)
                logger.info(f"Found pilot ID: {self.pilot_id}")
                return self.pilot_id
            else:
                raise ScrapingError(
                    "Could not find pilot ID. Make sure you're logged in correctly."
                )

        except requests.RequestException as e:
            raise ScrapingError(f"Failed to get pilot ID: {e}")

    def get_available_years(self) -> List[str]:
        """Get list of years (2026-2007, most recent first)"""
        years = [str(year) for year in range(2026, 2006, -1)]
        logger.info(f"Will check years: {years}")
        return years

    def _filter_flights(self, flights: List[IGCFlight], airport: str = None, min_points: float = None) -> List[IGCFlight]:
        """
        Filter flights by airport and/or minimum points

        Args:
            flights: List of flights to filter
            airport: Airport name for exact match filtering (case-insensitive)
            min_points: Minimum points score

        Returns:
            Filtered list of flights
        """
        filtered = flights

        if airport:
            # Substring match, case-insensitive (to handle variations like "Sterling MA (US / 1)")
            airport_lower = airport.lower()
            filtered = [f for f in filtered if f.airport and airport_lower in f.airport.lower()]
            logger.info(f"Filtered by airport '{airport}': {len(filtered)}/{len(flights)} flights")

        if min_points is not None:
            filtered = [f for f in filtered if f.points is not None and f.points >= min_points]
            logger.info(f"Filtered by min_points >= {min_points}: {len(filtered)}/{len(flights)} flights")

        return filtered

    def get_flights_for_year(self, year: str, airport: str = None, min_points: float = None) -> List[IGCFlight]:
        """
        Get all flights for a specific year using Scrapy + Playwright

        Args:
            year: Year string (e.g., "2024")
            airport: Filter by airport name (exact match, case-insensitive)
            min_points: Filter by minimum points score

        Returns:
            List of IGCFlight objects
        """
        pilot_id = self._get_pilot_id()

        logger.info(f"Using Scrapy + Playwright to fetch flights for year {year}...")

        try:
            # Use Scrapy with Playwright to scrape the JavaScript-rendered page
            runner = ScrapyRunner(self.session)
            scraped_items = runner.run_spider(pilot_id=pilot_id, year=year)

            flights = []
            for item in scraped_items:
                if item.get('needs_resolution'):
                    # This is a dsId that needs to be resolved to a flightId
                    # For now, skip these
                    logger.debug(f"Skipping item that needs resolution: {item}")
                    continue

                flights.append(IGCFlight(
                    url=item['download_url'],
                    filename=item['filename'],
                    date=item['date'],
                    year=item['year'],
                    flight_id=item['flight_id'],
                    dsid=item.get('dsid'),
                    referer=item.get('referer'),  # Include referer for download
                    airport=item.get('airport'),  # Takeoff airport
                    points=item.get('points'),  # Points score
                    distance=item.get('distance'),  # Distance in km from OLC
                    speed=item.get('speed'),  # Speed in km/h from OLC
                    aircraft=item.get('aircraft'),  # Aircraft type from OLC
                ))

            # Apply filters if specified
            flights = self._filter_flights(flights, airport=airport, min_points=min_points)

            logger.info(f"Found {len(flights)} flights for year {year}")
            return flights

        except Exception as e:
            logger.error(f"Error scraping year {year}: {e}")
            raise ScrapingError(f"Failed to get flights for year {year}: {e}")

    def get_all_flights_incremental(self, airport: str = None, min_points: float = None):
        """
        Generator that yields personal flights year by year (most recent first)

        This allows for incremental processing - download flights as soon as they're scraped.

        Args:
            airport: Filter by airport name (exact match, case-insensitive)
            min_points: Filter by minimum points score

        Yields:
            Tuple of (year, flights) for each year with flights
        """
        years = self.get_available_years()

        for year in years:
            try:
                flights = self.get_flights_for_year(year, airport=airport, min_points=min_points)
                if flights:
                    logger.info(f"Found {len(flights)} flights for year {year}")
                    yield (year, flights)
                else:
                    logger.info(f"No flights found for year {year}")

                # Be nice to the server - wait longer between years
                logger.info("Waiting 10 seconds before next year...")
                time.sleep(10)

            except ScrapingError as e:
                logger.warning(f"Skipping year {year}: {e}")
                continue

    def get_all_flights(self, airport: str = None, min_points: float = None) -> Dict[str, List[IGCFlight]]:
        """
        Get all flights for all available years (2026-2007, most recent first)

        Note: This scrapes all years before downloading. For incremental processing,
        use get_all_flights_incremental() instead.

        Args:
            airport: Filter by airport name (exact match, case-insensitive)
            min_points: Filter by minimum points score

        Returns:
            Dictionary mapping year to list of flights
        """
        all_flights = {}
        for year, flights in self.get_all_flights_incremental(airport, min_points):
            all_flights[year] = flights

        total = sum(len(flights) for flights in all_flights.values())
        logger.info(f"Found total of {total} flights across {len(all_flights)} years")

        return all_flights

    def get_public_flights_by_airport_incremental(self, airport_code: str, year: str = None, min_points: float = None, output_dir: str = None):
        """
        Generator that yields public flights from ALL pilots at a specific airport, year by year

        This allows for incremental processing - download flights as soon as they're scraped
        instead of scraping all years first.

        Args:
            airport_code: OLC airport code (e.g., 'STAUB1' for Saint Auban)
            year: Year to search (if None, searches all available years)
            min_points: Filter by minimum points score
            output_dir: Output directory (used to check for already downloaded flights)

        Yields:
            Tuple of (year, flights) for each year with flights
        """
        from .scrapy_runner import ScrapyRunner

        if year:
            years = [year]
        else:
            years = self.get_available_years()

        for year_val in years:
            try:
                logger.info(f"Using Scrapy + Playwright to fetch public flights for airport {airport_code}, year {year_val}...")

                # Use airport spider to scrape public flights
                runner = ScrapyRunner(self.session)
                scraped_items = runner.run_airport_spider(
                    airport_code=airport_code,
                    year=year_val,
                    min_points=min_points,
                    output_dir=output_dir
                )

                flights = []
                for item in scraped_items:
                    flights.append(IGCFlight(
                        url=item['download_url'],
                        filename=item['filename'],
                        date=item['date'],
                        year=item['year'],
                        flight_id=item['flight_id'],
                        dsid=item.get('dsid'),
                        referer=item.get('referer'),
                        airport=item.get('airport'),
                        points=item.get('points'),
                        pilot=item.get('pilot'),  # Include pilot name
                        distance=item.get('distance'),  # Distance in km from OLC
                        speed=item.get('speed'),  # Speed in km/h from OLC
                        aircraft=item.get('aircraft'),  # Aircraft type from OLC
                    ))

                # Note: min_points filtering is now done in the spider before following flightinfo links

                if flights:
                    logger.info(f"Found {len(flights)} public flights for airport {airport_code}, year {year_val}")
                    yield (year_val, flights)
                else:
                    logger.info(f"No public flights found for airport {airport_code}, year {year_val}")

                # Be nice to the server - wait longer between years
                logger.info("Waiting 10 seconds before next year...")
                time.sleep(10)

            except Exception as e:
                logger.error(f"Error scraping public flights for year {year_val}: {e}")
                logger.warning(f"Skipping year {year_val}")
                continue

    def get_public_flights_by_airport(self, airport_code: str, year: str = None, min_points: float = None) -> Dict[str, List[IGCFlight]]:
        """
        Get all public flights from ALL pilots at a specific airport

        Note: This scrapes all years before downloading. For incremental processing,
        use get_public_flights_by_airport_incremental() instead.

        Args:
            airport_code: OLC airport code (e.g., 'STAUB1' for Saint Auban)
            year: Year to search (if None, searches all available years)
            min_points: Filter by minimum points score

        Returns:
            Dictionary mapping year to list of flights
        """
        all_flights = {}
        for year_val, flights in self.get_public_flights_by_airport_incremental(airport_code, year, min_points):
            all_flights[year_val] = flights

        total = sum(len(flights) for flights in all_flights.values())
        logger.info(f"Found total of {total} public flights from {len(all_flights)} years")

        return all_flights

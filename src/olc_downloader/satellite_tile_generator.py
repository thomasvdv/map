"""
Satellite Tile Generator for Date-Specific Imagery

This module handles downloading and caching NASA GIBS VIIRS satellite tiles
for specific flight dates, allowing pilots to review cloud conditions and
weather from the day they flew.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import List, Set, Tuple, Optional
import json

logger = logging.getLogger(__name__)


class SatelliteTileManager:
    """Manages generation and caching of date-specific satellite tiles from NASA GIBS."""

    # VIIRS data available from 2012 onwards
    VIIRS_START_DATE = datetime(2012, 1, 19)

    # MODIS Terra data available from 2000 onwards
    MODIS_START_DATE = datetime(2000, 2, 24)

    # NASA GIBS URL patterns (VIIRS preferred, MODIS as fallback)
    GIBS_VIIRS_URL_TEMPLATE = (
        "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
        "VIIRS_SNPP_CorrectedReflectance_TrueColor/default/"
        "{date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg"
    )

    GIBS_MODIS_URL_TEMPLATE = (
        "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
        "MODIS_Terra_CorrectedReflectance_TrueColor/default/"
        "{date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg"
    )

    def __init__(self, base_dir: Path):
        """
        Initialize the satellite tile manager.

        Args:
            base_dir: Base directory for tile storage (e.g., daily_sat_tiles/)
        """
        self.base_dir = Path(base_dir)
        self.satellite_tiles_dir = self.base_dir
        self.satellite_tiles_dir.mkdir(parents=True, exist_ok=True)

    def get_unique_flight_dates(self, downloads_dir: Path, airport_code: Optional[str] = None) -> Set[str]:
        """
        Extract unique flight dates from metadata files.

        Args:
            downloads_dir: Directory containing flight downloads
            airport_code: Optional airport code to filter (e.g., 'STERL1')

        Returns:
            Set of dates in YYYY-MM-DD format
        """
        dates = set()
        downloads_path = Path(downloads_dir)

        # Handle both personal flights (downloads/YYYY/) and airport flights (downloads/AIRPORT/YYYY/)
        search_dirs = []

        if airport_code:
            # Look in specific airport directory
            airport_dir = downloads_path / airport_code
            if airport_dir.exists():
                search_dirs.append(airport_dir)
        else:
            # Look in all directories
            search_dirs.extend([d for d in downloads_path.iterdir() if d.is_dir()])

        for search_dir in search_dirs:
            # Look for year directories
            for year_dir in search_dir.iterdir():
                if not year_dir.is_dir():
                    continue

                # Check if this is a year directory (4 digits)
                if not year_dir.name.isdigit() or len(year_dir.name) != 4:
                    continue

                # Look for metadata.json
                metadata_file = year_dir / "metadata.json"
                if not metadata_file.exists():
                    continue

                try:
                    with open(metadata_file, 'r') as f:
                        metadata = json.load(f)

                    # Extract dates from flights
                    for flight in metadata.get('flights', []):
                        date_str = flight.get('date')
                        if date_str:
                            # Convert DD.MM.YYYY to YYYY-MM-DD
                            try:
                                date_normalized = self._normalize_date(date_str)
                                if date_normalized:
                                    dates.add(date_normalized)
                            except ValueError as e:
                                logger.warning(f"Could not parse date '{date_str}': {e}")

                except (json.JSONDecodeError, IOError) as e:
                    logger.warning(f"Could not read metadata from {metadata_file}: {e}")

        return dates

    def _normalize_date(self, date_str: str) -> Optional[str]:
        """
        Convert date string to YYYY-MM-DD format.

        Args:
            date_str: Date in DD.MM.YYYY or YYYY-MM-DD format

        Returns:
            Date in YYYY-MM-DD format, or None if invalid
        """
        # Try DD.MM.YYYY format (from metadata)
        if '.' in date_str:
            parts = date_str.split('.')
            if len(parts) == 3:
                day, month, year = parts
                return f"{year}-{month.zfill(2)}-{day.zfill(2)}"

        # Try YYYY-MM-DD format (already normalized)
        if '-' in date_str and len(date_str) == 10:
            # Validate format
            datetime.strptime(date_str, '%Y-%m-%d')
            return date_str

        return None

    def filter_viirs_dates(self, dates: Set[str]) -> Tuple[Set[str], Set[str]]:
        """
        Filter dates into VIIRS-available and pre-VIIRS sets.

        Args:
            dates: Set of dates in YYYY-MM-DD format

        Returns:
            Tuple of (viirs_dates, pre_viirs_dates)
        """
        viirs_dates = set()
        pre_viirs_dates = set()

        for date_str in dates:
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d')
                if date >= self.VIIRS_START_DATE:
                    viirs_dates.add(date_str)
                else:
                    pre_viirs_dates.add(date_str)
            except ValueError:
                logger.warning(f"Invalid date format: {date_str}")

        return viirs_dates, pre_viirs_dates

    def get_nasa_gibs_url(self, date: str, z: int, x: int, y: int, use_modis: bool = False) -> str:
        """
        Construct NASA GIBS tile URL for specific date and coordinates.

        Args:
            date: Date in YYYY-MM-DD format
            z: Zoom level (0-9 for VIIRS native)
            x: Tile X coordinate
            y: Tile Y coordinate
            use_modis: If True, use MODIS Terra instead of VIIRS (for dates with VIIRS gaps)

        Returns:
            Full URL to tile image
        """
        if use_modis:
            return self.GIBS_MODIS_URL_TEMPLATE.format(date=date, z=z, x=x, y=y)
        else:
            return self.GIBS_VIIRS_URL_TEMPLATE.format(date=date, z=z, x=x, y=y)

    def get_tile_path(self, date: str, z: int, x: int, y: int) -> Path:
        """
        Get local filesystem path for a tile.

        Args:
            date: Date in YYYY-MM-DD format
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate

        Returns:
            Path to tile file
        """
        return self.satellite_tiles_dir / date / str(z) / str(x) / f"{y}.jpg"

    def tile_exists(self, date: str, z: int, x: int, y: int) -> bool:
        """
        Check if a tile already exists locally.

        Args:
            date: Date in YYYY-MM-DD format
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate

        Returns:
            True if tile exists
        """
        return self.get_tile_path(date, z, x, y).exists()

    def get_date_tile_directory(self, date: str) -> Path:
        """
        Get the directory containing all tiles for a specific date.

        Args:
            date: Date in YYYY-MM-DD format

        Returns:
            Path to date directory
        """
        return self.satellite_tiles_dir / date

    def get_generated_dates(self) -> Set[str]:
        """
        Get list of dates that have been generated.

        Returns:
            Set of dates in YYYY-MM-DD format
        """
        dates = set()
        if self.satellite_tiles_dir.exists():
            for date_dir in self.satellite_tiles_dir.iterdir():
                if date_dir.is_dir() and len(date_dir.name) == 10:
                    # Validate date format YYYY-MM-DD
                    try:
                        datetime.strptime(date_dir.name, '%Y-%m-%d')
                        dates.add(date_dir.name)
                    except ValueError:
                        pass
        return dates

"""Metadata storage for tracking downloaded flights"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set
from datetime import datetime

logger = logging.getLogger(__name__)


class FlightMetadata:
    """Metadata for a single flight"""

    def __init__(
        self,
        flight_id: str,
        dsid: str,
        date: str,
        pilot: str,
        airport: str,
        points: float,
        filename: str,
        download_url: str,
        downloaded_at: str = None,
        download_status: str = "downloaded",
        distance: float = None,
        speed: float = None,
        aircraft: str = None,
        **kwargs
    ):
        self.flight_id = flight_id
        self.dsid = dsid
        self.date = date
        self.pilot = pilot
        self.airport = airport
        self.points = points
        self.filename = filename
        self.download_url = download_url
        self.downloaded_at = downloaded_at or datetime.utcnow().isoformat()
        self.download_status = download_status  # "downloaded", "missing", "failed"
        self.distance = distance
        self.speed = speed
        self.aircraft = aircraft
        self.extra = kwargs

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            'flight_id': self.flight_id,
            'dsid': self.dsid,
            'date': self.date,
            'pilot': self.pilot,
            'airport': self.airport,
            'points': self.points,
            'filename': self.filename,
            'download_url': self.download_url,
            'downloaded_at': self.downloaded_at,
            'download_status': self.download_status,
            'distance': self.distance,
            'speed': self.speed,
            'aircraft': self.aircraft,
            **self.extra
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'FlightMetadata':
        """Create from dictionary"""
        return cls(**data)


class MetadataStore:
    """Manages flight metadata storage in JSON files"""

    METADATA_FILENAME = "metadata.json"

    def __init__(self, base_dir: Path):
        """
        Initialize metadata store

        Args:
            base_dir: Base directory for downloads (e.g., downloads/)
        """
        self.base_dir = Path(base_dir)

    def _get_metadata_path(self, airport_code: str, year: str) -> Path:
        """Get path to metadata file for airport/year"""
        if airport_code:
            return self.base_dir / airport_code / year / self.METADATA_FILENAME
        else:
            return self.base_dir / year / self.METADATA_FILENAME

    def load_metadata(self, airport_code: str, year: str) -> Dict[str, FlightMetadata]:
        """
        Load metadata for a specific airport/year

        Returns:
            Dictionary mapping dsid to FlightMetadata
        """
        metadata_path = self._get_metadata_path(airport_code, year)

        if not metadata_path.exists():
            logger.debug(f"No metadata file found at {metadata_path}")
            return {}

        try:
            with open(metadata_path, 'r') as f:
                data = json.load(f)

            # Convert to FlightMetadata objects, keyed by dsid
            metadata = {}
            for item in data.get('flights', []):
                flight = FlightMetadata.from_dict(item)
                metadata[flight.dsid] = flight

            logger.info(f"Loaded metadata for {len(metadata)} flights from {metadata_path}")
            return metadata

        except Exception as e:
            logger.error(f"Failed to load metadata from {metadata_path}: {e}")
            return {}

    def save_metadata(
        self,
        airport_code: str,
        year: str,
        flights: List[FlightMetadata]
    ):
        """
        Save metadata for a specific airport/year

        Args:
            airport_code: Airport code (or None for personal flights)
            year: Year string
            flights: List of FlightMetadata objects to save
        """
        metadata_path = self._get_metadata_path(airport_code, year)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            # Convert to list of dicts
            data = {
                'airport_code': airport_code,
                'year': year,
                'updated_at': datetime.utcnow().isoformat(),
                'flights': [flight.to_dict() for flight in flights]
            }

            with open(metadata_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.info(f"Saved metadata for {len(flights)} flights to {metadata_path}")

        except Exception as e:
            logger.error(f"Failed to save metadata to {metadata_path}: {e}")

    def add_flight(
        self,
        airport_code: str,
        year: str,
        flight: FlightMetadata
    ):
        """
        Add or update a single flight's metadata

        Args:
            airport_code: Airport code (or None for personal flights)
            year: Year string
            flight: FlightMetadata object to add
        """
        # Load existing metadata
        metadata = self.load_metadata(airport_code, year)

        # Add/update this flight
        metadata[flight.dsid] = flight

        # Save back
        self.save_metadata(airport_code, year, list(metadata.values()))

    def get_downloaded_dsids(self, airport_code: str, year: str) -> Set[str]:
        """
        Get set of dsids that have already been downloaded

        Args:
            airport_code: Airport code (or None for personal flights)
            year: Year string

        Returns:
            Set of dsids
        """
        metadata = self.load_metadata(airport_code, year)
        return set(metadata.keys())

    def has_flight(self, airport_code: str, year: str, dsid: str) -> bool:
        """
        Check if a flight has already been downloaded

        Args:
            airport_code: Airport code (or None for personal flights)
            year: Year string
            dsid: Flight dsid

        Returns:
            True if flight is in metadata (i.e., already downloaded)
        """
        downloaded = self.get_downloaded_dsids(airport_code, year)
        return dsid in downloaded

    def validate_and_fix_metadata(self, airport_code: str, year: str) -> tuple[int, int]:
        """
        Validate metadata against actual files and update download status.
        Marks flights as "missing" if the IGC file doesn't exist or is invalid.

        Args:
            airport_code: Airport code (or None for personal flights)
            year: Year string

        Returns:
            Tuple of (valid_count, missing_count)
        """
        metadata = self.load_metadata(airport_code, year)

        if not metadata:
            logger.info(f"No metadata to validate for {airport_code}/{year}")
            return 0, 0

        # Get directory path
        if airport_code:
            year_dir = self.base_dir / airport_code / year
        else:
            year_dir = self.base_dir / year

        valid_count = 0
        missing_count = 0
        updated = False

        for dsid, flight in metadata.items():
            file_path = year_dir / flight.filename

            # Check if file exists and is valid
            if file_path.exists():
                try:
                    # Quick validation: check it's not HTML and has IGC format
                    with open(file_path, 'r', encoding='latin-1') as f:
                        first_line = f.readline().strip()
                        if first_line.startswith('A') or first_line.startswith('H'):
                            # Valid IGC file
                            if flight.download_status != "downloaded":
                                flight.download_status = "downloaded"
                                updated = True
                            valid_count += 1
                        else:
                            # Invalid file (probably HTML error)
                            logger.warning(f"Invalid IGC file: {flight.filename}")
                            flight.download_status = "missing"
                            updated = True
                            missing_count += 1
                except Exception as e:
                    logger.warning(f"Could not validate file {flight.filename}: {e}")
                    flight.download_status = "missing"
                    updated = True
                    missing_count += 1
            else:
                # File doesn't exist
                if flight.download_status != "missing":
                    flight.download_status = "missing"
                    updated = True
                missing_count += 1

        # Save updated metadata if changed
        if updated:
            self.save_metadata(airport_code, year, list(metadata.values()))
            logger.info(f"Updated metadata for {airport_code}/{year}: {valid_count} valid, {missing_count} missing")

        return valid_count, missing_count

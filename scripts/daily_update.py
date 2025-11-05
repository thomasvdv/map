#!/usr/bin/env python3
"""
Daily Update Orchestration Script

Checks for new flights, downloads them,
regenerates the map, and prepares files for upload to R2.

Uses state tracking to avoid reprocessing already-handled dates and flights.
Designed for stateless CI/CD environments (GitHub Actions).
"""

import os
import sys
import argparse
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Set
import re

# Add parent directory to path to import olc_downloader
sys.path.insert(0, str(Path(__file__).parent.parent))

from state_manager import ProcessingState

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DailyUpdater:
    """Orchestrates daily flight updates with state tracking"""

    def __init__(self, airport_code: str, force: bool = False):
        self.airport_code = airport_code        self.force = force
        self.downloads_dir = Path('downloads') / airport_code
        # Initialize state management
        self.state = ProcessingState(airport_code)

        self.new_flights: List[str] = []
        self.new_dates: Set[str] = []
        self.skipped_flights = 0
        self.skipped_dates = 0

    def check_for_new_flights(self) -> int:
        """
        Check OLC for new flights.

        Returns:
            Number of new flights found
        """
        logger.info(f"Checking OLC for new flights at {self.airport_code}...")

        try:
            # Use the existing CLI to list flights
            cmd = [
                'python', '-m', 'olc_downloader.cli',
                'list',
                '--all-pilots',
                '--airport-code', self.airport_code,
                '--verbose'
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"Failed to list flights: {result.stderr}")
                return 0

            # Parse output to identify new flights
            logger.info("Flight listing successful")
            logger.debug(result.stdout)

            return 0  # Will be determined by download step

        except Exception as e:
            logger.error(f"Failed to check for new flights: {e}")
            return 0

    def download_new_flights(self) -> int:
        """
        Download new flights from OLC.

        Returns:
            Number of flights downloaded
        """
        logger.info(f"Downloading new flights for {self.airport_code}...")

        try:
            # Run the map command which downloads flights and generates the map
            cmd = [
                'python', '-m', 'olc_downloader.cli',
                'map',
                '--airport-code', self.airport_code,
                '--deployment-mode', 'static',                '--no-upload',  # Don't upload yet
                '--verbose'
            ]

            if self.force:
                cmd.append('--force')

            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=False, text=True)

            if result.returncode != 0:
                logger.error("Flight download/map generation failed")
                return 0

            # Count IGC files in the directory
            igc_files = list(self.downloads_dir.rglob('*.igc'))
            logger.info(f"Found {len(igc_files)} total flight files")

            # Filter to only new flights (not in state)
            if not self.force:
                new_igc_files = self.state.get_new_flights([f.name for f in igc_files])
                self.skipped_flights = len(igc_files) - len(new_igc_files)
                logger.info(f"New flights: {len(new_igc_files)}, Already processed: {self.skipped_flights}")
            else:
                new_igc_files = [f.name for f in igc_files]
                logger.info(f"Force mode: processing all {len(new_igc_files)} flights")

            
            # Mark new flights as processed
            for flight_name in new_igc_files:
                date_str = self.extract_date_from_filename(flight_name)
                if date_str:
                    self.state.mark_flight_processed(flight_name, date_str, uploaded_to_r2=False)

            # Save state
            self.state.save()

            self.new_flights = new_igc_files
            return len(new_igc_files)

        except Exception as e:
            logger.error(f"Failed to download flights: {e}")
            import traceback
            traceback.print_exc()
            return 0

    def extract_date_from_filename(self, filename: str) -> str:
        """
        Extract date from IGC filename.

        Args:
            filename: IGC filename (e.g., 2025_Pilot_Name_123.igc)

        Returns:
            Date string in YYYY-MM-DD format or None
        """
        try:
            # IGC filename format typically starts with YYYY_
            # Try to find a year at the start
            match = re.match(r'(\d{4})_', filename)
            if match:
                year = match.group(1)
                # For now, we'll need to read the IGC file to get the actual date
                # This is a simplified version - in production, parse the B records
                return None  # TODO: Implement proper date extraction

            return None
        except Exception as e:
            logger.debug(f"Could not extract date from {filename}: {e}")
            return None



    def write_summary(self, flights_downloaded: int) -> None:
        """
        Write a summary of the update.

        Args:
            flights_downloaded: Number of flights downloaded
        """
        summary_path = Path('update_summary.txt')

        with open(summary_path, 'w') as f:
            f.write(f"Daily Update Summary\n")
            f.write(f"===================\n")
            f.write(f"\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
            f.write(f"Airport: {self.airport_code}\n")
            f.write(f"\n")
            f.write(f"New flights downloaded: {flights_downloaded}\n")
            f.write(f"Flights skipped (already processed): {self.skipped_flights}\n")
            f.write(f"New flight dates: {len(self.new_dates)}\n")
            f.write(f"Dates skipped (already processed): {self.skipped_dates}\n")            f.write(f"\n")
            f.write(f"State Statistics:\n")
            f.write(f"  Total flights processed: {self.state.get_processed_flight_count()}\n")
            f.write(f"  Total dates with sat tiles: {self.state.get_processed_date_count()}\n")
            f.write(f"\n")
            if self.new_dates:
                f.write(f"New dates processed:\n")
                for date in sorted(self.new_dates):
                    f.write(f"  - {date}\n")

        logger.info(f"Summary written to {summary_path}")
        logger.info(f"\n{self.state.get_summary()}")

    def run(self) -> bool:
        """
        Run the daily update process.

        Returns:
            True if successful
        """
        logger.info("=== Starting Daily Update ===")
        logger.info(f"Airport: {self.airport_code}")        logger.info(f"Force regenerate: {self.force}")
        logger.info("")
        logger.info(self.state.get_summary())

        try:
            # Step 1: Check for new flights
            self.check_for_new_flights()

            # Step 2: Download new flights and generate map
            flights_downloaded = self.download_new_flights()

            if flights_downloaded == 0 and not self.force:
                logger.info("No new flights found")
                self.write_summary(0)
                return True

            
            # Step 4: Write summary
            self.write_summary(flights_downloaded)

            logger.info("=== Daily Update Complete ===")
            return True

        except Exception as e:
            logger.error(f"Daily update failed: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    parser = argparse.ArgumentParser(description='Daily OLC flight update with state tracking')
    parser.add_argument('--airport-code', '-a', required=True, help='Airport code (e.g., STERL1)')    parser.add_argument('--force', '-f', action='store_true', help='Force regenerate everything (ignore state)')
    args = parser.parse_args()

    updater = DailyUpdater(
        airport_code=args.airport_code,        force=args.force
    )

    success = updater.run()
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())

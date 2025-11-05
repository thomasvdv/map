#!/usr/bin/env python3
"""
Initialize State File

Populates the state file with all existing flights in the downloads directory.
Use this after initial setup to mark existing flights as already processed.
"""

import sys
import argparse
import logging
from pathlib import Path
import re

sys.path.insert(0, str(Path(__file__).parent.parent))

from state_manager import ProcessingState

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def extract_date_from_igc(igc_path: Path) -> str:
    """
    Extract date from IGC file HFDTE record.

    Args:
        igc_path: Path to IGC file

    Returns:
        Date string in YYYY-MM-DD format or None
    """
    try:
        with open(igc_path, 'r', errors='ignore') as f:
            for line in f:
                # HFDTE record formats:
                # Old format: HFDTEXXXXXX where XXXXXX is DDMMYY
                # New format: HFDTEDATE:DDMMYY,1
                if line.startswith('HFDTE'):
                    # Try new format first
                    if 'DATE:' in line:
                        # Format: HFDTEDATE:DDMMYY,1
                        parts = line.split(':')
                        if len(parts) >= 2:
                            date_part = parts[1].split(',')[0]  # Get DDMMYY
                            if len(date_part) == 6:
                                day = date_part[0:2]
                                month = date_part[2:4]
                                year = date_part[4:6]
                                # Assume 20XX
                                full_year = f"20{year}"
                                return f"{full_year}-{month}-{day}"
                    else:
                        # Old format: HFDTEXXXXXX
                        date_str = line[5:11]  # DDMMYY
                        if len(date_str) == 6 and date_str.isdigit():
                            day = date_str[0:2]
                            month = date_str[2:4]
                            year = date_str[4:6]
                            # Assume 20XX
                            full_year = f"20{year}"
                            return f"{full_year}-{month}-{day}"
        return None
    except Exception as e:
        logger.warning(f"Could not parse date from {igc_path}: {e}")
        return None


def initialize_state_from_downloads(airport_code: str, mark_sat_tiles: bool = False) -> None:
    """
    Initialize state file from existing downloads directory.

    Args:
        airport_code: Airport code
        mark_sat_tiles: Whether to mark all dates as having satellite tiles generated
    """
    downloads_dir = Path('downloads') / airport_code

    if not downloads_dir.exists():
        logger.error(f"Downloads directory not found: {downloads_dir}")
        sys.exit(1)

    logger.info(f"Initializing state for {airport_code} from {downloads_dir}")

    # Initialize state manager
    state = ProcessingState(airport_code)

    # Find all IGC files
    igc_files = list(downloads_dir.rglob('*.igc'))
    logger.info(f"Found {len(igc_files)} IGC files")

    dates_found = set()

    for igc_file in igc_files:
        # Extract date from file
        date_str = extract_date_from_igc(igc_file)

        if date_str:
            # Mark flight as processed
            state.mark_flight_processed(
                flight_filename=igc_file.name,
                date_str=date_str,
                uploaded_to_r2=True  # Assume already uploaded
            )

            dates_found.add(date_str)
            logger.debug(f"Marked {igc_file.name} as processed (date: {date_str})")
        else:
            logger.warning(f"Could not extract date from {igc_file.name}, skipping")

    logger.info(f"Marked {len(igc_files)} flights as processed")
    logger.info(f"Found {len(dates_found)} unique dates")

    # Optionally mark all dates as having satellite tiles
    if mark_sat_tiles:
        logger.info("Marking all dates as having satellite tiles generated")
        for date_str in dates_found:
            state.mark_date_processed(date_str, satellite_tiles_generated=True)

    # Save state
    if state.save():
        logger.info("State file initialized successfully!")
        logger.info(f"\n{state.get_summary()}")
    else:
        logger.error("Failed to save state file")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Initialize state file from existing downloads')
    parser.add_argument('--airport-code', '-a', required=True, help='Airport code (e.g., STERL1)')
    parser.add_argument('--mark-sat-tiles', action='store_true',
                        help='Mark all dates as having satellite tiles generated')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    initialize_state_from_downloads(args.airport_code, args.mark_sat_tiles)


if __name__ == '__main__':
    main()

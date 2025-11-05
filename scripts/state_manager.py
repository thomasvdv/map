#!/usr/bin/env python3
"""
State Management for OLC Flight Processing

Tracks which flights and dates have been processed to avoid redundant work.
State is stored in a JSON file and synced to R2 between runs.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Set, Dict, Optional, List

logger = logging.getLogger(__name__)


class ProcessingState:
    """Manages state of processed flights and dates"""

    def __init__(self, airport_code: str, state_file: Path = None):
        """
        Initialize state manager.

        Args:
            airport_code: Airport code (e.g., STERL1)
            state_file: Path to state file (defaults to downloads/{airport_code}_state.json)
        """
        self.airport_code = airport_code

        if state_file is None:
            self.state_file = Path('downloads') / f'{airport_code}_state.json'
        else:
            self.state_file = Path(state_file)

        self.state = self._load_state()

    def _load_state(self) -> dict:
        """
        Load state from file.

        Returns:
            State dictionary
        """
        if not self.state_file.exists():
            logger.info(f"No existing state file found at {self.state_file}, starting fresh")
            return self._create_empty_state()

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
                logger.info(f"Loaded state from {self.state_file}")
                return state
        except Exception as e:
            logger.error(f"Failed to load state file: {e}")
            logger.warning("Starting with fresh state")
            return self._create_empty_state()

    def _create_empty_state(self) -> dict:
        """Create empty state structure"""
        return {
            "airport_code": self.airport_code,
            "last_updated": None,
            "processed_dates": {},
            "processed_flights": {},
            "metadata": {
                "created_at": datetime.utcnow().isoformat() + 'Z',
                "version": "1.0"
            }
        }

    def save(self) -> bool:
        """
        Save state to file.

        Returns:
            True if successful
        """
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            # Update last_updated timestamp
            self.state['last_updated'] = datetime.utcnow().isoformat() + 'Z'

            with open(self.state_file, 'w') as f:
                json.dump(self.state, f, indent=2)

            logger.info(f"Saved state to {self.state_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            return False

    def is_flight_processed(self, flight_filename: str) -> bool:
        """
        Check if a flight has been processed.

        Args:
            flight_filename: IGC filename (e.g., 2025_Pilot_Name_123.igc)

        Returns:
            True if flight has been processed
        """
        return flight_filename in self.state['processed_flights']

    def is_date_processed(self, date_str: str) -> bool:
        """
        Check if a date has been fully processed (including satellite tiles).

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            True if date has been processed with satellite tiles
        """
        date_state = self.state['processed_dates'].get(date_str, {})
        return date_state.get('satellite_tiles_generated', False)

    def get_new_flights(self, all_flights: List[str]) -> List[str]:
        """
        Filter list of flights to only those not yet processed.

        Args:
            all_flights: List of flight filenames

        Returns:
            List of new flight filenames
        """
        return [f for f in all_flights if not self.is_flight_processed(f)]

    def get_new_dates(self, all_dates: Set[str]) -> Set[str]:
        """
        Filter set of dates to only those not yet processed.

        Args:
            all_dates: Set of dates in YYYY-MM-DD format

        Returns:
            Set of new dates
        """
        return {d for d in all_dates if not self.is_date_processed(d)}

    def mark_flight_processed(
        self,
        flight_filename: str,
        date_str: str,
        uploaded_to_r2: bool = True
    ) -> None:
        """
        Mark a flight as processed.

        Args:
            flight_filename: IGC filename
            date_str: Flight date in YYYY-MM-DD format
            uploaded_to_r2: Whether file was uploaded to R2
        """
        self.state['processed_flights'][flight_filename] = {
            'date': date_str,
            'uploaded_to_r2': uploaded_to_r2,
            'processed_at': datetime.utcnow().isoformat() + 'Z'
        }

        # Also add to date's flight list
        if date_str not in self.state['processed_dates']:
            self.state['processed_dates'][date_str] = {
                'flights': [],
                'satellite_tiles_generated': False,
                'last_processed': None
            }

        if flight_filename not in self.state['processed_dates'][date_str]['flights']:
            self.state['processed_dates'][date_str]['flights'].append(flight_filename)

        logger.debug(f"Marked flight as processed: {flight_filename}")

    def mark_date_processed(
        self,
        date_str: str,
        satellite_tiles_generated: bool = True
    ) -> None:
        """
        Mark a date as fully processed.

        Args:
            date_str: Date in YYYY-MM-DD format
            satellite_tiles_generated: Whether satellite tiles were generated
        """
        if date_str not in self.state['processed_dates']:
            self.state['processed_dates'][date_str] = {
                'flights': [],
                'satellite_tiles_generated': False,
                'last_processed': None
            }

        self.state['processed_dates'][date_str]['satellite_tiles_generated'] = satellite_tiles_generated
        self.state['processed_dates'][date_str]['last_processed'] = datetime.utcnow().isoformat() + 'Z'

        logger.debug(f"Marked date as processed: {date_str}")

    def get_processed_flight_count(self) -> int:
        """Get total number of processed flights"""
        return len(self.state['processed_flights'])

    def get_processed_date_count(self) -> int:
        """Get total number of processed dates"""
        return len([d for d in self.state['processed_dates'].values()
                    if d.get('satellite_tiles_generated', False)])

    def get_summary(self) -> str:
        """
        Get human-readable summary of state.

        Returns:
            Summary string
        """
        total_flights = len(self.state['processed_flights'])
        total_dates = len(self.state['processed_dates'])
        dates_with_tiles = len([d for d in self.state['processed_dates'].values()
                                if d.get('satellite_tiles_generated', False)])

        summary = f"Processing State for {self.airport_code}\n"
        summary += f"  Total flights processed: {total_flights}\n"
        summary += f"  Total dates tracked: {total_dates}\n"
        summary += f"  Dates with satellite tiles: {dates_with_tiles}\n"

        if self.state['last_updated']:
            summary += f"  Last updated: {self.state['last_updated']}\n"

        return summary

    def reset(self) -> None:
        """Reset state to empty"""
        logger.warning("Resetting state to empty")
        self.state = self._create_empty_state()

    def get_flights_for_date(self, date_str: str) -> List[str]:
        """
        Get list of processed flights for a specific date.

        Args:
            date_str: Date in YYYY-MM-DD format

        Returns:
            List of flight filenames
        """
        date_state = self.state['processed_dates'].get(date_str, {})
        return date_state.get('flights', [])


def main():
    """CLI for inspecting/managing state"""
    import argparse

    parser = argparse.ArgumentParser(description='Manage processing state')
    parser.add_argument('--airport-code', '-a', required=True, help='Airport code')
    parser.add_argument('--state-file', help='Path to state file')
    parser.add_argument('--action', choices=['show', 'reset'], default='show',
                        help='Action to perform')
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format='%(message)s')

    state = ProcessingState(args.airport_code, args.state_file)

    if args.action == 'show':
        print(state.get_summary())

        # Show recent dates
        if state.state['processed_dates']:
            print("\nRecent dates:")
            sorted_dates = sorted(state.state['processed_dates'].keys(), reverse=True)
            for date_str in sorted_dates[:10]:
                date_state = state.state['processed_dates'][date_str]
                tiles = "✓" if date_state.get('satellite_tiles_generated') else "✗"
                flight_count = len(date_state.get('flights', []))
                print(f"  {date_str}: {flight_count} flights, tiles: {tiles}")

    elif args.action == 'reset':
        confirm = input(f"Reset state for {args.airport_code}? (yes/no): ")
        if confirm.lower() == 'yes':
            state.reset()
            state.save()
            print("State reset successfully")
        else:
            print("Cancelled")


if __name__ == '__main__':
    main()

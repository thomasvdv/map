#!/usr/bin/env python3
"""
Manual Update Orchestration Script

Generates a map for a specific airport/year with optional filters.
Handles git commits automatically.

Can be run from GitHub Actions or command line.
"""

import os
import sys
import argparse
import logging
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ManualUpdater:
    """Orchestrates manual map generation with optional commits"""

    def __init__(self, airport_code: str, year: Optional[str] = None,
                 min_points: Optional[int] = None, skip_download: bool = False,
                 force: bool = False, skip_commit: bool = False,
                 workflow_type: str = "manual"):
        self.airport_code = airport_code
        self.year = year
        self.min_points = min_points
        self.skip_download = skip_download
        self.force = force
        self.skip_commit = skip_commit
        self.workflow_type = workflow_type

    def generate_map(self) -> bool:
        """
        Generate map using the CLI.

        Returns:
            True if successful
        """
        logger.info(f"Generating map for {self.airport_code}...")
        logger.info("Satellite imagery served directly from NASA GIBS")

        try:
            # Build CLI command
            cmd = [
                'python', '-m', 'olc_downloader.cli',
                'map',
                '--airport-code', self.airport_code,
                '--deployment-mode', 'static',
                '--no-upload',  # Don't upload yet
                '--verbose'
            ]

            if self.year:
                cmd.extend(['--year', self.year])
            if self.min_points:
                cmd.extend(['--min-points', str(self.min_points)])
            if self.skip_download:
                cmd.append('--skip-download')
            if self.force:
                cmd.append('--force')

            logger.info(f"Running: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=False, text=True)

            if result.returncode != 0:
                logger.error("Map generation failed")
                return False

            logger.info("Map generation successful")
            return True

        except Exception as e:
            logger.error(f"Failed to generate map: {e}")
            import traceback
            traceback.print_exc()
            return False

    def commit_and_push(self) -> bool:
        """
        Commit and push IGC files, metadata, and state to git.

        Returns:
            True if successful or skipped, False on error
        """
        if self.skip_commit:
            logger.info("Skipping git commit (--skip-commit flag)")
            return True

        logger.info("Committing and pushing flight data to git...")

        try:
            # Call the commit script
            script_path = Path(__file__).parent / 'commit_and_push_flights.sh'
            run_number = os.getenv('GITHUB_RUN_NUMBER', str(int(datetime.now().timestamp())))

            cmd = [
                str(script_path),
                self.airport_code,
                self.workflow_type,
                run_number
            ]

            result = subprocess.run(cmd, capture_output=False, text=True)

            if result.returncode != 0:
                logger.error("Failed to commit and push changes")
                return False

            logger.info("Successfully committed and pushed changes")
            return True

        except Exception as e:
            logger.error(f"Failed to commit and push: {e}")
            import traceback
            traceback.print_exc()
            return False

    def run(self) -> bool:
        """
        Run the manual update process.

        Returns:
            True if successful
        """
        logger.info("=== Starting Manual Update ===")
        logger.info(f"Airport: {self.airport_code}")
        logger.info(f"Year: {self.year or 'all'}")
        logger.info(f"Min points: {self.min_points or 'none'}")
        logger.info(f"Skip download: {self.skip_download}")
        logger.info(f"Force regenerate: {self.force}")
        logger.info("")

        try:
            # Step 1: Generate map
            if not self.generate_map():
                logger.error("Map generation failed")
                return False

            # Step 2: Commit and push changes
            if not self.commit_and_push():
                logger.warning("Failed to commit changes, but continuing...")

            logger.info("=== Manual Update Complete ===")
            return True

        except Exception as e:
            logger.error(f"Manual update failed: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    parser = argparse.ArgumentParser(description='Manual map generation with integrated git commits')
    parser.add_argument('--airport-code', '-a', required=True, help='Airport code (e.g., STERL1)')
    parser.add_argument('--year', '-y', help='Specific year to process')
    parser.add_argument('--min-points', type=int, help='Minimum points filter')
    parser.add_argument('--skip-download', action='store_true', help='Skip downloading flights')
    parser.add_argument('--force', '-f', action='store_true', help='Force regenerate everything')
    parser.add_argument('--skip-commit', action='store_true', help='Skip git commit and push')
    parser.add_argument('--workflow-type', default='manual', help='Workflow type (daily, manual, local)')
    args = parser.parse_args()

    updater = ManualUpdater(
        airport_code=args.airport_code,
        year=args.year,
        min_points=args.min_points,
        skip_download=args.skip_download,
        force=args.force,
        skip_commit=args.skip_commit,
        workflow_type=args.workflow_type
    )

    success = updater.run()
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""
R2 Sync Utilities for GitHub Actions

Handles downloading/uploading data to/from Cloudflare R2 for stateless CI/CD workflows.
"""

import os
import sys
import argparse
import logging
from pathlib import Path
from typing import List, Set
import json

# Add parent directory to path to import olc_downloader
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from src.olc_downloader.r2_uploader import R2Uploader
except ImportError:
    print("Error: Could not import R2Uploader. Make sure boto3 is installed and the package is properly set up.")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class R2Sync:
    """Sync utilities for R2 storage"""

    def __init__(self):
        self.uploader = R2Uploader()
        self.downloads_dir = Path('downloads')
        self.sat_tiles_dir = Path('daily_sat_tiles')

    def download_metadata(self) -> bool:
        """
        Download flight metadata from R2.

        This downloads the JSON metadata files that track which flights exist.
        """
        logger.info("Downloading flight metadata from R2...")

        try:
            # Download all JSON metadata files from maps/ directory
            import boto3
            from botocore.exceptions import ClientError

            s3 = self.uploader.s3_client
            bucket = self.uploader.bucket

            # List all JSON files in maps/
            try:
                response = s3.list_objects_v2(Bucket=bucket, Prefix='maps/')
                if 'Contents' not in response:
                    logger.warning("No metadata files found in R2")
                    return False

                metadata_files = [obj['Key'] for obj in response['Contents'] if obj['Key'].endswith('.json')]

                if not metadata_files:
                    logger.warning("No JSON metadata files found")
                    return False

                # Download each metadata file
                self.downloads_dir.mkdir(exist_ok=True)
                for key in metadata_files:
                    local_path = self.downloads_dir / Path(key).name
                    logger.info(f"Downloading {key} -> {local_path}")
                    s3.download_file(bucket, key, str(local_path))

                logger.info(f"Downloaded {len(metadata_files)} metadata files")
                return True

            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code == '404':
                    logger.warning("No metadata found in R2 (first run?)")
                    return False
                raise

        except Exception as e:
            logger.error(f"Failed to download metadata: {e}")
            return False

    def download_recent_flights(self, days: int = 30) -> bool:
        """
        Download recent flight IGC files from R2.

        Args:
            days: Number of days of recent flights to download

        Returns:
            True if successful
        """
        logger.info(f"Downloading recent flights (last {days} days) from R2...")

        try:
            import boto3
            from datetime import datetime, timedelta
            from botocore.exceptions import ClientError

            s3 = self.uploader.s3_client
            bucket = self.uploader.bucket

            # Calculate cutoff date
            cutoff = datetime.now() - timedelta(days=days)

            # List all IGC files
            try:
                response = s3.list_objects_v2(Bucket=bucket, Prefix='flights/')
                if 'Contents' not in response:
                    logger.info("No flights found in R2")
                    return True  # Not an error, just no flights yet

                recent_flights = []
                for obj in response['Contents']:
                    if obj['Key'].endswith('.igc'):
                        # Check if file is recent
                        if obj['LastModified'].replace(tzinfo=None) >= cutoff:
                            recent_flights.append(obj['Key'])

                if not recent_flights:
                    logger.info(f"No flights from last {days} days found")
                    return True

                # Download each flight
                self.downloads_dir.mkdir(exist_ok=True)
                for key in recent_flights:
                    local_path = self.downloads_dir / Path(key).name
                    logger.debug(f"Downloading {key} -> {local_path}")
                    s3.download_file(bucket, key, str(local_path))

                logger.info(f"Downloaded {len(recent_flights)} recent flight files")
                return True

            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', '')
                if error_code == '404':
                    logger.info("No flights directory in R2 (first run?)")
                    return True
                raise

        except Exception as e:
            logger.error(f"Failed to download recent flights: {e}")
            return False

    def download_all_flights(self) -> bool:
        """
        Download ALL flight IGC files from R2.

        Use this for full map regeneration.
        """
        logger.info("Downloading all flights from R2...")

        try:
            import boto3
            from botocore.exceptions import ClientError

            s3 = self.uploader.s3_client
            bucket = self.uploader.bucket

            # List all IGC files
            response = s3.list_objects_v2(Bucket=bucket, Prefix='flights/')
            if 'Contents' not in response:
                logger.info("No flights found in R2")
                return True

            flights = [obj['Key'] for obj in response['Contents'] if obj['Key'].endswith('.igc')]

            if not flights:
                logger.info("No flight files found")
                return True

            # Download each flight
            self.downloads_dir.mkdir(exist_ok=True)
            for i, key in enumerate(flights):
                local_path = self.downloads_dir / Path(key).name
                if i % 50 == 0:
                    logger.info(f"Downloading flights: {i}/{len(flights)}")
                s3.download_file(bucket, key, str(local_path))

            logger.info(f"Downloaded {len(flights)} flight files")
            return True

        except Exception as e:
            logger.error(f"Failed to download all flights: {e}")
            return False

    def upload_new_files(self) -> bool:
        """
        Upload new/changed files to R2.

        Uses the existing R2Uploader with deduplication.
        """
        logger.info("Uploading new/changed files to R2...")

        try:
            total_uploaded = 0
            total_skipped = 0

            # Upload satellite tiles (if any)
            if self.sat_tiles_dir.exists():
                logger.info("Uploading satellite tiles...")
                uploaded, skipped, total = self.uploader.upload_satellite_tiles(self.sat_tiles_dir)
                logger.info(f"  Satellite tiles: {uploaded} uploaded, {skipped} skipped, {total} total")
                total_uploaded += uploaded
                total_skipped += skipped

            # Upload maps
            maps = list(self.downloads_dir.glob('*_map.html'))
            if maps:
                logger.info("Uploading maps...")
                for map_file in maps:
                    success = self.uploader.upload_map(map_file)
                    if success:
                        total_uploaded += 1
                        logger.info(f"  Uploaded: {map_file.name}")
                    else:
                        logger.warning(f"  Failed to upload: {map_file.name}")

            # Upload flight metadata
            metadata_files = list(self.downloads_dir.glob('*.json'))
            if metadata_files:
                logger.info("Uploading metadata files...")
                for meta_file in metadata_files:
                    uploaded, skipped = self.uploader.upload_file(
                        meta_file,
                        f"maps/{meta_file.name}",
                        content_type="application/json",
                        cache_control="public, max-age=3600"
                    )
                    if uploaded:
                        total_uploaded += 1
                    elif skipped:
                        total_skipped += 1

            # Upload IGC files (new flights only)
            igc_files = list(self.downloads_dir.glob('*.igc'))
            if igc_files:
                logger.info(f"Uploading {len(igc_files)} IGC files...")
                for igc_file in igc_files:
                    uploaded, skipped = self.uploader.upload_file(
                        igc_file,
                        f"flights/{igc_file.name}",
                        content_type="application/octet-stream",
                        cache_control="public, max-age=31536000"
                    )
                    if uploaded:
                        total_uploaded += 1
                    elif skipped:
                        total_skipped += 1

            logger.info(f"Upload complete: {total_uploaded} uploaded, {total_skipped} skipped")
            return True

        except Exception as e:
            logger.error(f"Failed to upload files: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description='Sync data with Cloudflare R2')
    parser.add_argument('action', choices=['download', 'upload'], help='Action to perform')
    parser.add_argument('--include-flights', action='store_true', help='Download all flight IGC files (not just metadata)')
    parser.add_argument('--recent-days', type=int, default=30, help='Download flights from last N days (default: 30)')
    args = parser.parse_args()

    sync = R2Sync()

    if args.action == 'download':
        logger.info("=== Downloading from R2 ===")

        # Always download metadata
        success = sync.download_metadata()

        # Optionally download flights
        if args.include_flights:
            success = sync.download_all_flights() and success
        else:
            # Just download recent flights for context
            success = sync.download_recent_flights(days=args.recent_days) and success

        if success:
            logger.info("Download complete")
            return 0
        else:
            logger.error("Download failed")
            return 1

    elif args.action == 'upload':
        logger.info("=== Uploading to R2 ===")

        if sync.upload_new_files():
            logger.info("Upload complete")
            return 0
        else:
            logger.error("Upload failed")
            return 1


if __name__ == '__main__':
    sys.exit(main())

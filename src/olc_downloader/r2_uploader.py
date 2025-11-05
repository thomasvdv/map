"""
Cloudflare R2 Uploader

Handles uploading VFR tiles and maps to Cloudflare R2 storage.
Satellite imagery is served directly from NASA GIBS (no upload needed).
Uses boto3 (S3-compatible API) for uploads.
"""

import os
import logging
import hashlib
from pathlib import Path
from typing import Optional, List, Tuple
import boto3
from botocore.exceptions import ClientError
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

logger = logging.getLogger(__name__)


class R2Uploader:
    """Handles uploads to Cloudflare R2 storage"""

    def __init__(
        self,
        account_id: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        bucket: str = "map",
        public_domain: Optional[str] = None
    ):
        """
        Initialize R2 uploader.

        Args:
            account_id: Cloudflare account ID (or from R2_ACCOUNT_ID env var)
            access_key_id: R2 access key ID (or from R2_ACCESS_KEY_ID env var)
            secret_access_key: R2 secret access key (or from R2_SECRET_ACCESS_KEY env var)
            bucket: R2 bucket name (default: 'map')
            public_domain: R2 public domain (or from R2_PUBLIC_DOMAIN env var)
        """
        self.account_id = account_id or os.getenv('R2_ACCOUNT_ID')
        self.access_key_id = access_key_id or os.getenv('R2_ACCESS_KEY_ID')
        self.secret_access_key = secret_access_key or os.getenv('R2_SECRET_ACCESS_KEY')
        self.bucket = bucket
        self.public_domain = public_domain or os.getenv('R2_PUBLIC_DOMAIN') or 'pub-32af5705466c411d82c79b436565f4a9.r2.dev'

        if not self.account_id:
            raise ValueError("R2_ACCOUNT_ID not provided. Set R2_ACCOUNT_ID environment variable.")
        if not self.access_key_id:
            raise ValueError("R2_ACCESS_KEY_ID not provided. Set R2_ACCESS_KEY_ID environment variable.")
        if not self.secret_access_key:
            raise ValueError("R2_SECRET_ACCESS_KEY not provided. Set R2_SECRET_ACCESS_KEY environment variable.")

        # Initialize S3 client for R2
        self.endpoint_url = f"https://{self.account_id}.r2.cloudflarestorage.com"
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name='auto'  # R2 uses 'auto' region
        )

        logger.info(f"Initialized R2 uploader for bucket '{self.bucket}' at {self.endpoint_url}")

    def _calculate_md5(self, file_path: Path) -> str:
        """
        Calculate MD5 checksum of a local file.

        Args:
            file_path: Path to local file

        Returns:
            MD5 checksum as hex string
        """
        hash_md5 = hashlib.md5()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def _file_exists_with_same_content(self, remote_path: str, local_path: Path) -> bool:
        """
        Check if a file exists in R2 with the same content as local file.

        Args:
            remote_path: Remote path in bucket
            local_path: Local file path

        Returns:
            True if file exists in R2 with same MD5 checksum, False otherwise
        """
        try:
            # Get object metadata from R2
            response = self.s3_client.head_object(
                Bucket=self.bucket,
                Key=remote_path
            )

            # Get ETag (MD5 hash) from R2 object
            # ETag is returned with quotes, so strip them
            remote_etag = response['ETag'].strip('"')

            # Calculate local file MD5
            local_md5 = self._calculate_md5(local_path)

            # Compare checksums
            return remote_etag == local_md5

        except ClientError as e:
            # File doesn't exist or other error
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code == '404':
                return False
            else:
                logger.warning(f"Error checking file existence for {remote_path}: {e}")
                return False

    def upload_file(
        self,
        local_path: Path,
        remote_path: str,
        content_type: Optional[str] = None,
        cache_control: str = "public, max-age=31536000",
        acl: str = "public-read",
        skip_if_exists: bool = True
    ) -> Tuple[bool, bool]:
        """
        Upload a single file to R2.

        Args:
            local_path: Local file path
            remote_path: Remote path in bucket (e.g., 'vfr_tiles/tiles/8/73/98.png')
            content_type: MIME type (auto-detected if None)
            cache_control: Cache-Control header
            acl: Access control (public-read or private)
            skip_if_exists: If True, skip upload if file exists with same content (default: True)

        Returns:
            Tuple of (uploaded, skipped) booleans
            - (True, False) = file was uploaded
            - (False, True) = file was skipped (already exists with same content)
            - (False, False) = upload failed
        """
        try:
            # Check if file already exists with same content
            if skip_if_exists and self._file_exists_with_same_content(remote_path, local_path):
                logger.debug(f"Skipping {remote_path} (already exists with same content)")
                return (False, True)

            # Auto-detect content type if not provided
            if content_type is None:
                if local_path.suffix == '.png':
                    content_type = 'image/png'
                elif local_path.suffix == '.jpg' or local_path.suffix == '.jpeg':
                    content_type = 'image/jpeg'
                elif local_path.suffix == '.html':
                    content_type = 'text/html'
                elif local_path.suffix == '.json':
                    content_type = 'application/json'
                else:
                    content_type = 'application/octet-stream'

            extra_args = {
                'ContentType': content_type,
                'CacheControl': cache_control,
                'ACL': acl
            }

            self.s3_client.upload_file(
                str(local_path),
                self.bucket,
                remote_path,
                ExtraArgs=extra_args
            )
            logger.debug(f"Uploaded {remote_path}")
            return (True, False)

        except ClientError as e:
            logger.error(f"Failed to upload {local_path}: {e}")
            return (False, False)

    def upload_directory(
        self,
        local_dir: Path,
        remote_prefix: str,
        pattern: str = "*",
        content_type: Optional[str] = None,
        cache_control: str = "public, max-age=31536000",
        show_progress: bool = True,
        skip_if_exists: bool = True
    ) -> Tuple[int, int, int]:
        """
        Upload a directory to R2.

        Args:
            local_dir: Local directory path
            remote_prefix: Remote prefix in bucket (e.g., 'vfr_tiles/tiles/')
            pattern: File pattern to match (default: '*' for all files)
            content_type: MIME type (auto-detected if None)
            cache_control: Cache-Control header
            show_progress: Show progress bar
            skip_if_exists: If True, skip files that already exist with same content (default: True)

        Returns:
            Tuple of (uploaded_count, skipped_count, total_count)
        """
        local_dir = Path(local_dir)
        if not local_dir.exists():
            raise ValueError(f"Directory not found: {local_dir}")

        # Find all files matching pattern
        if '**' in pattern:
            files = list(local_dir.rglob(pattern.replace('**/', '')))
        else:
            files = list(local_dir.glob(pattern))

        if not files:
            logger.warning(f"No files found matching pattern '{pattern}' in {local_dir}")
            return 0, 0, 0

        logger.info(f"Processing {len(files)} files from {local_dir} to {remote_prefix}")

        uploaded_count = 0
        skipped_count = 0

        if show_progress:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
            ) as progress:
                task = progress.add_task(f"Uploading to R2...", total=len(files))

                for file_path in files:
                    # Calculate relative path for remote
                    relative_path = file_path.relative_to(local_dir)
                    remote_path = f"{remote_prefix.rstrip('/')}/{relative_path}"

                    uploaded, skipped = self.upload_file(
                        file_path, remote_path, content_type, cache_control, skip_if_exists=skip_if_exists
                    )
                    if uploaded:
                        uploaded_count += 1
                    elif skipped:
                        skipped_count += 1

                    progress.update(task, advance=1)
        else:
            for file_path in files:
                relative_path = file_path.relative_to(local_dir)
                remote_path = f"{remote_prefix.rstrip('/')}/{relative_path}"

                uploaded, skipped = self.upload_file(
                    file_path, remote_path, content_type, cache_control, skip_if_exists=skip_if_exists
                )
                if uploaded:
                    uploaded_count += 1
                elif skipped:
                    skipped_count += 1

        logger.info(
            f"Upload complete: {uploaded_count} uploaded, {skipped_count} skipped, "
            f"{len(files) - uploaded_count - skipped_count} failed, {len(files)} total"
        )
        return uploaded_count, skipped_count, len(files)

    def upload_vfr_tiles(
        self,
        vfr_tiles_dir: Path,
        show_progress: bool = True,
        skip_if_exists: bool = True
    ) -> Tuple[int, int, int]:
        """
        Upload VFR sectional tiles to R2.

        Args:
            vfr_tiles_dir: Path to vfr_tiles directory
            show_progress: Show progress bar
            skip_if_exists: If True, skip files that already exist with same content (default: True)

        Returns:
            Tuple of (uploaded_count, skipped_count, total_count)
        """
        tiles_dir = vfr_tiles_dir / "tiles"
        if not tiles_dir.exists():
            raise ValueError(f"VFR tiles directory not found: {tiles_dir}")

        return self.upload_directory(
            tiles_dir,
            "vfr_tiles/tiles/",
            pattern="**/*.png",
            content_type="image/png",
            show_progress=show_progress,
            skip_if_exists=skip_if_exists
        )

    def upload_map(
        self,
        map_file: Path,
        remote_name: Optional[str] = None,
        skip_if_exists: bool = True
    ) -> bool:
        """
        Upload a map HTML file to R2.

        Args:
            map_file: Path to map HTML file
            remote_name: Optional remote filename (defaults to map_file.name)
            skip_if_exists: If True, skip upload if file exists with same content (default: True)

        Returns:
            True if successful, False otherwise
        """
        if not map_file.exists():
            raise ValueError(f"Map file not found: {map_file}")

        remote_name = remote_name or map_file.name
        # Upload index.html to root, other maps to maps/ subdirectory
        if remote_name == 'index.html':
            remote_path = remote_name
        else:
            remote_path = f"maps/{remote_name}"

        logger.info(f"Uploading map {map_file.name} to {remote_path}")

        uploaded, skipped = self.upload_file(
            map_file,
            remote_path,
            content_type="text/html",
            cache_control="public, max-age=3600",  # 1 hour cache for maps
            skip_if_exists=skip_if_exists
        )

        if skipped:
            logger.info(f"Map {map_file.name} already exists with same content (skipped)")

        return uploaded or skipped

    def get_public_url(self, remote_path: str) -> str:
        """
        Get public URL for an uploaded file.

        Args:
            remote_path: Remote path in bucket

        Returns:
            Public URL (using R2.dev or custom domain)
        """
        # Use configured public domain (from env var or default R2.dev domain)
        return f"https://{self.public_domain}/{remote_path}"

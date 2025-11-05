"""Configuration management for OLC Downloader"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from .exceptions import ConfigurationError


class Config:
    """Configuration manager for OLC Downloader"""

    def __init__(self):
        self.config_dir = Path.home() / ".olc-downloader"
        self.config_file = self.config_dir / "config.env"
        self.config_dir.mkdir(exist_ok=True)

        # Load environment variables from config file if it exists
        if self.config_file.exists():
            load_dotenv(self.config_file)

    def get_credentials(self) -> tuple[str, str]:
        """Get OLC credentials from environment or config file"""
        username = os.getenv("OLC_USERNAME")
        password = os.getenv("OLC_PASSWORD")

        if not username or not password:
            raise ConfigurationError(
                "Credentials not found. Set OLC_USERNAME and OLC_PASSWORD environment variables "
                f"or create {self.config_file} with these values."
            )

        return username, password

    def save_credentials(self, username: str, password: str):
        """Save credentials to config file"""
        with open(self.config_file, "w") as f:
            f.write(f"OLC_USERNAME={username}\n")
            f.write(f"OLC_PASSWORD={password}\n")

        # Set restrictive permissions on config file
        os.chmod(self.config_file, 0o600)

    def get_download_dir(self, custom_path: Optional[str] = None) -> Path:
        """Get download directory path"""
        if custom_path:
            return Path(custom_path)

        download_dir = os.getenv("OLC_DOWNLOAD_DIR", "./downloads")
        return Path(download_dir)

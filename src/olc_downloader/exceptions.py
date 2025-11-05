"""Custom exceptions for OLC Downloader"""


class OLCDownloaderError(Exception):
    """Base exception for OLC Downloader"""
    pass


class AuthenticationError(OLCDownloaderError):
    """Raised when authentication fails"""
    pass


class ScrapingError(OLCDownloaderError):
    """Raised when scraping/parsing fails"""
    pass


class DownloadError(OLCDownloaderError):
    """Raised when download fails"""
    pass


class ConfigurationError(OLCDownloaderError):
    """Raised when configuration is invalid"""
    pass


class RateLimitError(OLCDownloaderError):
    """Raised when daily download limit is reached"""
    pass

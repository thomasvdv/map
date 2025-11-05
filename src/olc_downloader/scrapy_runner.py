"""Utility to run Scrapy spiders programmatically using subprocess"""

import logging
import json
import subprocess
import sys
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


class ScrapyRunner:
    """Helper class to run Scrapy spiders programmatically"""

    def __init__(self, session):
        self.session = session

    def run_spider(self, pilot_id: str, year: str) -> list:
        """
        Run the OLC flightbook spider for a specific year in a subprocess

        Args:
            pilot_id: OLC pilot ID
            year: Year to scrape

        Returns:
            List of scraped flight data dictionaries
        """
        # Convert requests session cookies to JSON format
        cookies = []
        for cookie in self.session.cookies:
            cookies.append({
                'name': cookie.name,
                'value': cookie.value,
                'domain': cookie.domain,
                'path': cookie.path,
            })

        # Create a temporary file to store results
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as f:
            results_file = f.name

        try:
            # Run spider in subprocess
            logger.info(f"Running Scrapy spider for year {year}...")

            # Create the subprocess script
            script = f"""
import sys
import json

# Install asyncio reactor before importing Scrapy
if 'twisted.internet.reactor' not in sys.modules:
    import twisted.internet.asyncioreactor
    twisted.internet.asyncioreactor.install()

from scrapy.crawler import CrawlerProcess
from scrapy import signals

# Import spider
from olc_downloader.spiders.olc_spider import OLCFlightbookSpider

# Configuration
pilot_id = {repr(pilot_id)}
year = {repr(year)}
cookies = {repr(cookies)}
user_agent = {repr(self.session.headers.get('User-Agent', 'Mozilla/5.0'))}
results_file = {repr(results_file)}

# Scrapy settings
settings = {{
    'LOG_LEVEL': 'INFO',
    'USER_AGENT': user_agent,
    'ROBOTSTXT_OBEY': False,
    'CONCURRENT_REQUESTS': 1,
    'DOWNLOAD_DELAY': 5,  # Increased from 2 to 5 seconds between requests
    'COOKIES_ENABLED': True,
    'DOWNLOAD_HANDLERS': {{
        'http': 'scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler',
        'https': 'scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler',
    }},
    'PLAYWRIGHT_BROWSER_TYPE': 'chromium',
    'PLAYWRIGHT_LAUNCH_OPTIONS': {{
        'headless': True,
    }},
    'TWISTED_REACTOR': 'twisted.internet.asyncioreactor.AsyncioSelectorReactor',
    'REQUEST_FINGERPRINTER_IMPLEMENTATION': '2.7',
}}

# Collect results
results = []

def item_scraped(item, response, spider):
    results.append(dict(item))

# Create and run crawler
process = CrawlerProcess(settings=settings)
crawler = process.create_crawler(OLCFlightbookSpider)
crawler.signals.connect(item_scraped, signal=signals.item_scraped)

process.crawl(crawler, pilot_id=pilot_id, year=year, cookies=cookies)
process.start()

# Save results
with open(results_file, 'w') as f:
    json.dump(results, f)
"""

            # Run the script with streaming output
            logger.info(f"Starting Playwright browser for flightbook spider (this may take 1-2 minutes)...")
            result = subprocess.run(
                [sys.executable, '-c', script],
                capture_output=False,  # Stream output to console
                text=True,
                timeout=600  # 10 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"Spider subprocess failed with return code {result.returncode}")
                raise RuntimeError(f"Spider failed with return code {result.returncode}")

            # Read results
            with open(results_file, 'r') as f:
                results = json.load(f)

            logger.info(f"Spider finished. Collected {len(results)} items")
            return results

        finally:
            # Clean up temp file
            try:
                Path(results_file).unlink()
            except:
                pass

    def run_airport_spider(self, airport_code: str, year: str, min_points: float = None, output_dir: str = None) -> list:
        """
        Run the OLC airport flights spider for a specific year in a subprocess

        Args:
            airport_code: OLC airport code (e.g., 'STAUB1')
            year: Year to scrape
            min_points: Minimum points threshold (filter in spider before following links)
            output_dir: Output directory to check for existing metadata

        Returns:
            List of scraped flight data dictionaries
        """
        # Convert requests session cookies to JSON format
        cookies = []
        for cookie in self.session.cookies:
            cookies.append({
                'name': cookie.name,
                'value': cookie.value,
                'domain': cookie.domain,
                'path': cookie.path,
            })

        # Create a temporary file to store results
        with tempfile.NamedTemporaryFile(mode='w+', suffix='.json', delete=False) as f:
            results_file = f.name

        try:
            # Run spider in subprocess
            logger.info(f"Running Scrapy airport spider for {airport_code}, year {year}...")

            # Create the subprocess script
            script = f"""
import sys
import json

# Install asyncio reactor before importing Scrapy
if 'twisted.internet.reactor' not in sys.modules:
    import twisted.internet.asyncioreactor
    twisted.internet.asyncioreactor.install()

from scrapy.crawler import CrawlerProcess
from scrapy import signals

# Import spider
from olc_downloader.spiders.airport_spider import OLCAirportFlightsSpider

# Configuration
airport_code = {repr(airport_code)}
year = {repr(year)}
min_points = {repr(min_points)}
output_dir = {repr(str(output_dir) if output_dir else None)}
cookies = {repr(cookies)}
user_agent = {repr(self.session.headers.get('User-Agent', 'Mozilla/5.0'))}
results_file = {repr(results_file)}

# Scrapy settings
settings = {{
    'LOG_LEVEL': 'INFO',
    'USER_AGENT': user_agent,
    'ROBOTSTXT_OBEY': False,
    'CONCURRENT_REQUESTS': 1,
    'DOWNLOAD_DELAY': 5,
    'COOKIES_ENABLED': True,
    'DOWNLOAD_HANDLERS': {{
        'http': 'scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler',
        'https': 'scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler',
    }},
    'PLAYWRIGHT_BROWSER_TYPE': 'chromium',
    'PLAYWRIGHT_LAUNCH_OPTIONS': {{
        'headless': True,
    }},
    'TWISTED_REACTOR': 'twisted.internet.asyncioreactor.AsyncioSelectorReactor',
    'REQUEST_FINGERPRINTER_IMPLEMENTATION': '2.7',
}}

# Collect results
results = []

def item_scraped(item, response, spider):
    results.append(dict(item))

# Create and run crawler
process = CrawlerProcess(settings=settings)
crawler = process.create_crawler(OLCAirportFlightsSpider)
crawler.signals.connect(item_scraped, signal=signals.item_scraped)

process.crawl(crawler, airport_code=airport_code, year=year, cookies=cookies, min_points=min_points, output_dir=output_dir)
process.start()

# Save results
with open(results_file, 'w') as f:
    json.dump(results, f)
"""

            # Run the script with streaming output
            logger.info(f"Starting Playwright browser for airport spider (this may take 1-2 minutes)...")
            result = subprocess.run(
                [sys.executable, '-c', script],
                capture_output=False,  # Stream output to console
                text=True,
                timeout=600  # 10 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"Airport spider subprocess failed with return code {result.returncode}")
                raise RuntimeError(f"Spider failed with return code {result.returncode}")

            # Read results
            with open(results_file, 'r') as f:
                results = json.load(f)

            logger.info(f"Airport spider finished. Collected {len(results)} items")
            return results

        finally:
            # Clean up temp file
            try:
                Path(results_file).unlink()
            except:
                pass

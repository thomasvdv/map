"""Scrapy spider for OLC flightbook with Playwright support"""

import scrapy
from scrapy_playwright.page import PageMethod
import re
import logging

logger = logging.getLogger(__name__)


class OLCFlightbookSpider(scrapy.Spider):
    name = "olc_flightbook"

    custom_settings = {
        'DOWNLOAD_HANDLERS': {
            "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
            "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
        },
        'PLAYWRIGHT_BROWSER_TYPE': 'chromium',
        'PLAYWRIGHT_LAUNCH_OPTIONS': {
            'headless': True,
        },
        'CONCURRENT_REQUESTS': 1,  # Be nice to the server
        'DOWNLOAD_DELAY': 2,
    }

    def __init__(self, pilot_id=None, year=None, cookies=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pilot_id = pilot_id
        self.year = year
        self.cookies = cookies or []

        if not self.pilot_id:
            raise ValueError("pilot_id is required")
        if not self.year:
            raise ValueError("year is required")

    def start_requests(self):
        """Start request for the flightbook page"""
        url = (
            f"https://www.onlinecontest.org/olc-3.0/gliding/flightbook.html"
            f"?rt=olc&st=olcp&pi={self.pilot_id}&sp={self.year}"
        )

        logger.info(f"Fetching flightbook for year {self.year}, pilot {self.pilot_id}")

        yield scrapy.Request(
            url,
            callback=self.parse,
            errback=self.errback,
            cookies={cookie['name']: cookie['value'] for cookie in self.cookies},
            meta={
                "playwright": True,
                "playwright_page_methods": [
                    # Just wait for page to load, don't require specific selectors
                    PageMethod("wait_for_load_state", "networkidle"),
                    # Give extra time for JavaScript to populate the table
                    PageMethod("wait_for_timeout", 5000),
                ],
                "playwright_include_page": True,  # Include page object for debugging
            },
        )

    async def errback(self, failure):
        """Handle errors and save debug info"""
        logger.error(f"Request failed: {failure}")
        page = failure.request.meta.get("playwright_page")
        if page:
            try:
                # Save screenshot and HTML for debugging
                screenshot_path = f'/tmp/olc_error_{self.year}.png'
                html_path = f'/tmp/olc_error_{self.year}.html'

                await page.screenshot(path=screenshot_path)
                html = await page.content()
                with open(html_path, 'w') as f:
                    f.write(html)

                logger.info(f"Saved error screenshot to {screenshot_path}")
                logger.info(f"Saved error HTML to {html_path}")
            except Exception as e:
                logger.error(f"Failed to save debug info: {e}")

    def parse(self, response):
        """Parse the flightbook page and extract flight data"""
        logger.info(f"Parsing response for year {self.year}")
        logger.debug(f"Response URL: {response.url}")
        logger.debug(f"Response length: {len(response.text)} chars")

        # Save HTML for debugging
        debug_file = f'/tmp/olc_success_{self.year}.html'
        with open(debug_file, 'w') as f:
            f.write(response.text)
        logger.info(f"Saved page HTML to {debug_file} for debugging")

        # Look for download links
        download_links = response.css('a[href*="download.html?flightId="]')
        logger.info(f"Found {len(download_links)} download links")

        for link in download_links:
            href = link.attrib.get('href', '')
            flight_id_match = re.search(r'flightId=(-?\d+)', href)

            if flight_id_match:
                flight_id = flight_id_match.group(1)

                # Get full URL
                download_url = response.urljoin(href)

                # Try to extract date, airport, and points from surrounding context
                # Look at the parent row
                parent_row = link.xpath('./ancestor::tr[1]')
                date = "unknown"
                airport = None
                points = None

                if parent_row:
                    row_text = parent_row.xpath('.//text()').getall()
                    row_text = ' '.join([t.strip() for t in row_text if t.strip()])

                    # Look for date patterns
                    date_patterns = [
                        r'(\d{4}-\d{2}-\d{2})',  # 2024-03-15
                        r'(\d{2}\.\d{2}\.\d{4})',  # 15.03.2024
                        r'(\d{1,2}/\d{1,2}/\d{4})',  # 3/15/2024
                    ]

                    for pattern in date_patterns:
                        match = re.search(pattern, row_text)
                        if match:
                            date = match.group(1)
                            break

                    # Extract airport from data-cn="takeoff" cell
                    takeoff_cell = parent_row[0].xpath('.//td[@data-cn="takeoff"]//a/text()')
                    if takeoff_cell:
                        airport = takeoff_cell.get().strip()

                    # Extract points from data-cn="points" cell
                    points_cell = parent_row[0].xpath('.//td[@data-cn="points"]/text()')
                    if points_cell:
                        try:
                            points = float(points_cell.get().strip())
                        except (ValueError, AttributeError):
                            points = None

                    # Extract distance from data-cn="distance" cell
                    distance_cell = parent_row[0].xpath('.//td[@data-cn="distance"]/text()')
                    distance = None
                    if distance_cell:
                        try:
                            distance = float(distance_cell.get().strip())
                        except (ValueError, AttributeError):
                            distance = None

                    # Extract speed from data-cn="speed" cell
                    speed_cell = parent_row[0].xpath('.//td[@data-cn="speed"]/text()')
                    speed = None
                    if speed_cell:
                        try:
                            speed = float(speed_cell.get().strip())
                        except (ValueError, AttributeError):
                            speed = None

                    # Extract aircraft from data-cn="plane" cell
                    aircraft_cell = parent_row[0].xpath('.//td[@data-cn="plane"]/text()')
                    aircraft = None
                    if aircraft_cell:
                        aircraft = aircraft_cell.get().strip()

                yield {
                    'flight_id': flight_id,
                    'download_url': download_url,
                    'date': date,
                    'year': self.year,
                    'filename': f"{self.year}_{flight_id}.igc",
                    'airport': airport,
                    'points': points,
                    'distance': distance,
                    'speed': speed,
                    'aircraft': aircraft,
                }

        # Alternative: Look for flightinfo links with dsId
        if not download_links:
            logger.info("No direct download links found, looking for flightinfo links...")
            flightinfo_links = response.css('a[href*="flightinfo.html?dsId="]')
            logger.info(f"Found {len(flightinfo_links)} flightinfo links")

            # Get unique dsIds only (avoid duplicates from comment icons)
            seen_dsids = set()
            for link in flightinfo_links:
                href = link.attrib.get('href', '')
                dsid_match = re.search(r'dsId=(-?\d+)', href)

                if dsid_match:
                    dsid = dsid_match.group(1)
                    if dsid in seen_dsids:
                        continue
                    seen_dsids.add(dsid)

                    flightinfo_url = response.urljoin(href.split('#')[0])  # Remove fragment

                    # Extract flight data from the table row BEFORE following the link
                    parent_row = link.xpath('./ancestor::tr[1]')
                    airport = None
                    points = None
                    distance = None
                    speed = None
                    aircraft = None

                    if parent_row:
                        # Extract airport from data-cn="takeoff" cell
                        takeoff_cell = parent_row[0].xpath('.//td[@data-cn="takeoff"]//a/text()')
                        if takeoff_cell:
                            airport = takeoff_cell.get().strip()

                        # Extract points from data-cn="points" cell
                        points_cell = parent_row[0].xpath('.//td[@data-cn="points"]/text()')
                        if points_cell:
                            try:
                                # Points text may be like "231.62 " or have spans, so split and take first part
                                points_text = points_cell.get().strip().split()[0]
                                points = float(points_text)
                            except (ValueError, AttributeError, IndexError):
                                points = None

                        # Extract distance from data-cn="distance" cell
                        distance_cell = parent_row[0].xpath('.//td[@data-cn="distance"]/text()')
                        if distance_cell:
                            try:
                                distance = float(distance_cell.get().strip())
                            except (ValueError, AttributeError):
                                distance = None

                        # Extract speed from data-cn="speed" cell
                        speed_cell = parent_row[0].xpath('.//td[@data-cn="speed"]/text()')
                        if speed_cell:
                            try:
                                speed = float(speed_cell.get().strip())
                            except (ValueError, AttributeError):
                                speed = None

                        # Extract aircraft from data-cn="plane" cell
                        aircraft_cell = parent_row[0].xpath('.//td[@data-cn="plane"]/text()')
                        if aircraft_cell:
                            aircraft = aircraft_cell.get().strip()

                    # Follow the flightinfo link to get the download URL
                    # Use regular HTTP request (no Playwright) since flightinfo pages are simpler
                    logger.info(f"Following flightinfo link for dsId {dsid}")
                    yield scrapy.Request(
                        flightinfo_url,
                        callback=self.parse_flightinfo,
                        cookies={cookie['name']: cookie['value'] for cookie in self.cookies},
                        meta={
                            "dsid": dsid,
                            "year": self.year,
                            "airport": airport,
                            "points": points,
                            "distance": distance,
                            "speed": speed,
                            "aircraft": aircraft,
                        },
                    )

        # Log if we found nothing
        if not download_links and not flightinfo_links:
            logger.warning(f"No flight links found for year {self.year}")

    def parse_flightinfo(self, response):
        """Parse flightinfo page to extract download link"""
        dsid = response.meta.get('dsid')
        year = response.meta.get('year')
        # Get flight data from meta (extracted from flightbook table)
        airport = response.meta.get('airport')
        points = response.meta.get('points')
        distance = response.meta.get('distance')
        speed = response.meta.get('speed')
        aircraft = response.meta.get('aircraft')

        logger.info(f"Parsing flightinfo for dsId {dsid}")

        # Look for download link on the flightinfo page
        # Prefer IGC file download (without kmlfile parameter) over KML
        download_links = response.css('a[href*="download.html?flightId="]')

        # Filter to get IGC link (not KML)
        igc_link = None
        for link in download_links:
            href = link.attrib.get('href', '')
            if 'kmlfile' not in href:
                igc_link = link
                break

        if igc_link:
            href = igc_link.attrib.get('href', '')
            flight_id_match = re.search(r'flightId=(-?\d+)', href)

            if flight_id_match:
                flight_id = flight_id_match.group(1)
                download_url = response.urljoin(href)

                # Extract date from the page
                date = "unknown"
                date_patterns = [
                    r'(\d{4}-\d{2}-\d{2})',  # 2024-03-15
                    r'(\d{2}\.\d{2}\.\d{4})',  # 15.03.2024
                    r'(\d{1,2}/\d{1,2}/\d{4})',  # 3/15/2024
                ]

                for pattern in date_patterns:
                    match = re.search(pattern, response.text[:5000])  # Search in first 5KB
                    if match:
                        date = match.group(1)
                        break

                # If airport/points weren't passed from flightbook, try to extract from flightinfo page
                if not airport:
                    airport_elem = response.css('a[href*="airportInfo.html"]::text').get()
                    if airport_elem:
                        airport = airport_elem.strip()

                if points is None:
                    points_match = re.search(r'Points[:\s]+(\d+\.?\d*)', response.text[:5000], re.IGNORECASE)
                    if points_match:
                        try:
                            points = float(points_match.group(1))
                        except ValueError:
                            pass

                logger.info(f"Found download URL for dsId {dsid}: flightId={flight_id}")

                yield {
                    'flight_id': flight_id,
                    'download_url': download_url,
                    'date': date,
                    'year': year,
                    'filename': f"{year}_{flight_id}.igc",
                    'dsid': dsid,
                    'referer': response.url,  # Include referer for download
                    'airport': airport,
                    'points': points,
                    'distance': distance,
                    'speed': speed,
                    'aircraft': aircraft,
                }
        else:
            logger.warning(f"No download link found on flightinfo page for dsId {dsid}")

"""Scrapy spider for OLC public airport flights using JSON API"""

import scrapy
import re
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)


class OLCAirportFlightsSpider(scrapy.Spider):
    name = "olc_airport_flights"

    custom_settings = {
        'CONCURRENT_REQUESTS': 1,  # Be nice to the server
        'DOWNLOAD_DELAY': 2,
        # Override Playwright handlers - we're using direct HTTP
        'DOWNLOAD_HANDLERS': {
            'http': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
            'https': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
        },
    }

    def __init__(self, airport_code=None, year=None, cookies=None, min_points=None, output_dir=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.airport_code = airport_code
        self.year = year
        self.cookies = cookies or []
        self.min_points = min_points  # Filter by minimum points
        self.output_dir = Path(output_dir) if output_dir else None
        self.downloaded_dsids = set()  # Track already downloaded flights

        if not self.airport_code:
            raise ValueError("airport_code is required")
        if not self.year:
            raise ValueError("year is required")

        # Load existing metadata to skip already downloaded flights
        if self.output_dir:
            self._load_existing_metadata()

    def _load_existing_metadata(self):
        """Load existing metadata AND scan filesystem to determine which flights are already downloaded"""
        year_dir = self.output_dir / self.airport_code / self.year
        metadata_path = year_dir / "metadata.json"

        from_metadata = 0
        from_filesystem = 0

        # Step 1: Load from metadata.json
        if metadata_path.exists():
            try:
                with open(metadata_path, 'r') as f:
                    data = json.load(f)

                for flight in data.get('flights', []):
                    dsid = flight.get('dsid')
                    filename = flight.get('filename')

                    if dsid and filename:
                        # Verify the file actually exists and is valid
                        file_path = year_dir / filename
                        if file_path.exists():
                            # Quick validation: check it's not HTML
                            try:
                                with open(file_path, 'r', encoding='latin-1') as f:
                                    first_line = f.readline().strip()
                                    # Only skip if it's a valid IGC file
                                    if first_line.startswith('A') or first_line.startswith('H'):
                                        self.downloaded_dsids.add(dsid)
                                        from_metadata += 1
                                    else:
                                        logger.debug(f"Skipping invalid file in metadata: {filename}")
                            except:
                                # If we can't read it, don't trust it
                                logger.debug(f"Could not validate file in metadata: {filename}")

            except Exception as e:
                logger.warning(f"Failed to load metadata from {metadata_path}: {e}")
        else:
            logger.info(f"No existing metadata found at {metadata_path}")

        # Step 2: Scan filesystem for IGC files not in metadata
        # This catches files that were downloaded but metadata is incomplete/missing
        if year_dir.exists():
            for igc_file in year_dir.glob("*.igc"):
                # Extract dsid from filename
                # Format is typically: YEAR_PILOT_DSID.igc or similar
                # dsid is usually the last part before .igc
                filename_parts = igc_file.stem.split('_')

                if len(filename_parts) >= 2:
                    # Try last part as dsid (most common format)
                    potential_dsid = filename_parts[-1]

                    # Only add if not already in our set (from metadata)
                    if potential_dsid not in self.downloaded_dsids:
                        # Validate it's a real IGC file
                        try:
                            with open(igc_file, 'r', encoding='latin-1') as f:
                                first_line = f.readline().strip()
                                if first_line.startswith('A') or first_line.startswith('H'):
                                    self.downloaded_dsids.add(potential_dsid)
                                    from_filesystem += 1
                                    logger.debug(f"Added {potential_dsid} from filesystem scan: {igc_file.name}")
                        except:
                            logger.debug(f"Could not validate file from filesystem: {igc_file.name}")

        total_flights = len(self.downloaded_dsids)
        logger.info(f"Loaded {total_flights} already downloaded flights ({from_metadata} from metadata, {from_filesystem} from filesystem scan)")

        if from_filesystem > 0:
            logger.info(f"Found {from_filesystem} flights in filesystem not in metadata - will not re-scrape these")

    def start_requests(self):
        """Start request using JSON API for pagination"""
        url = (
            f"https://www.onlinecontest.org/olc-3.0/gliding/flightsOfAirfield.html"
            f"?aa={self.airport_code}&st=olcp&rt=olc&c=C0&sc=&sp={self.year}"
        )

        logger.info(f"Fetching public flights for airport {self.airport_code}, year {self.year}")
        logger.info(f"Using JSON API with pagination")
        logger.info(f"URL: {url}")
        logger.info(f"Cookies: {len(self.cookies)} cookies provided")
        logger.info(f"Min points filter: {self.min_points}")
        logger.info(f"Output dir: {self.output_dir}")
        logger.info(f"Already downloaded: {len(self.downloaded_dsids)} flights")

        # First request to get initial batch and determine total
        yield scrapy.Request(
            url,
            method='POST',
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
                'Origin': 'https://www.onlinecontest.org',
                'Referer': url,
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-origin',
            },
            body='{"q":"ds","offset":0}',
            callback=self.parse_json_batch,
            errback=self.errback,
            cookies={cookie['name']: cookie['value'] for cookie in self.cookies},
            meta={'offset': 0, 'batch': 1},
            dont_filter=True,  # Allow duplicate requests for pagination
        )

    def errback(self, failure):
        """Handle errors"""
        logger.error(f"Request failed: {failure}")

    def parse_json_batch(self, response):
        """Parse JSON API response and handle pagination"""
        offset = response.meta.get('offset', 0)
        batch = response.meta.get('batch', 1)

        try:
            data = json.loads(response.text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response text: {response.text[:500]}")
            return

        # Check if data has the expected structure
        if not isinstance(data, dict):
            logger.error(f"Unexpected JSON structure: {type(data)}")
            return

        # Extract rows - API returns {'result': [...], 'count': N}
        rows = data.get('result', [])
        total = data.get('count', len(rows))

        logger.info(f"Batch {batch} (offset {offset}): Got {len(rows)} rows, total={total}")

        # Process this batch
        for row in rows:
            # Extract dsid from the row - JSON API uses 'id' field
            dsid = row.get('id')

            if not dsid:
                logger.debug(f"Row missing id: {row}")
                continue

            # Check if already downloaded
            if dsid in self.downloaded_dsids:
                logger.debug(f"Skipping already downloaded flight dsid={dsid}")
                continue

            # Extract points for filtering
            points_value = row.get('points')
            points = None
            if points_value is not None:
                try:
                    points = float(points_value)
                except (ValueError, TypeError):
                    pass

            # Filter by min_points if specified
            if self.min_points is not None:
                if points is None or points < self.min_points:
                    logger.debug(f"Skipping flight {dsid} with {points} points (below threshold {self.min_points})")
                    continue

            # Extract distance (in km)
            distance_value = row.get('distance')
            distance = None
            if distance_value is not None:
                try:
                    distance = float(distance_value)
                except (ValueError, TypeError):
                    pass

            # Extract speed (in km/h)
            speed_value = row.get('speed')
            speed = None
            if speed_value is not None:
                try:
                    speed = float(speed_value)
                except (ValueError, TypeError):
                    pass

            # Extract aircraft
            aircraft_value = row.get('plane')
            aircraft = None
            if aircraft_value is not None:
                aircraft = str(aircraft_value).strip() if aircraft_value else None

            # Extract other fields
            date = row.get('date', 'unknown')

            # Extract pilot name - API returns nested object like {"firstName": "John", "surName": "Doe"}
            pilot_obj = row.get('pilot', {})
            if isinstance(pilot_obj, dict):
                first_name = pilot_obj.get('firstName', '')
                sur_name = pilot_obj.get('surName', '')
                pilot = f"{first_name} {sur_name}".strip() or 'Unknown'
            else:
                pilot = str(pilot_obj) if pilot_obj else 'Unknown'

            airport = f"Airport {self.airport_code}"

            # Get flightinfo URL - construct from dsid
            flightinfo_url = f"https://www.onlinecontest.org/olc-3.0/gliding/flightinfo.html?dsId={dsid}"

            logger.info(f"Following flightinfo link for dsId {dsid}, pilot {pilot}, points {points}")
            yield scrapy.Request(
                flightinfo_url,
                callback=self.parse_flightinfo,
                cookies={cookie['name']: cookie['value'] for cookie in self.cookies},
                meta={
                    "dsid": dsid,
                    "year": self.year,
                    "distance": distance,
                    "speed": speed,
                    "aircraft": aircraft,
                    "airport": airport,
                    "points": points,
                    "date": date,
                    "pilot": pilot,
                },
            )

        # Check if we need more batches
        next_offset = offset + len(rows)
        if next_offset < total:
            limit = min(50, total - next_offset)
            url = response.url

            logger.info(f"Fetching next batch: offset={next_offset}, limit={limit}")
            yield scrapy.Request(
                url,
                method='POST',
                headers={
                    'Accept': 'application/json',
                    'Content-Type': 'application/json',
                    'Origin': 'https://www.onlinecontest.org',
                    'Referer': url,
                    'sec-fetch-dest': 'empty',
                    'sec-fetch-mode': 'cors',
                    'sec-fetch-site': 'same-origin',
                },
                body=json.dumps({"q":"ds","offset":next_offset,"limit":limit}),
                callback=self.parse_json_batch,
                errback=self.errback,
                cookies={cookie['name']: cookie['value'] for cookie in self.cookies},
                meta={'offset': next_offset, 'batch': batch + 1},
                dont_filter=True,
            )
        else:
            logger.info(f"✓ All batches fetched! Total rows processed: {total}")

    def parse(self, response):
        """Parse the public airport flights page and extract flight data"""
        logger.info(f"Parsing public flights for airport {self.airport_code}, year {self.year}")
        logger.debug(f"Response URL: {response.url}")
        logger.debug(f"Response length: {len(response.text)} chars")

        # Save HTML for debugging
        debug_file = f'/tmp/olc_airport_{self.airport_code}_{self.year}.html'
        with open(debug_file, 'w') as f:
            f.write(response.text)
        logger.info(f"Saved page HTML to {debug_file} for debugging")

        # Look for flight rows in the table
        # Public airport pages use similar structure to flightbook

        # Try different selectors - check both visible and all rows
        flight_rows = response.css('tr[data-rid]')
        logger.info(f"Found {len(flight_rows)} flight rows with 'tr[data-rid]'")

        # Also check if there are hidden rows
        all_trs_in_tbody = response.xpath('//tbody//tr')
        logger.info(f"Total tr elements in tbody: {len(all_trs_in_tbody)}")

        # Check for pagination or row count info
        row_info = response.xpath('//text()[contains(., "rows") or contains(., "entries") or contains(., "Showing")]').getall()
        if row_info:
            logger.info(f"Pagination info found: {row_info[:3]}")  # Log first 3 matches

        if not flight_rows:
            # Try alternative selectors
            flight_rows = response.xpath('//tr[@data-rid]')
            logger.info(f"Found {len(flight_rows)} flight rows with XPath '//tr[@data-rid]'")

        if not flight_rows:
            # Try to find any tr with data-rid in tbody
            flight_rows = response.xpath('//tbody/tr[@data-rid]')
            logger.info(f"Found {len(flight_rows)} flight rows with XPath '//tbody/tr[@data-rid]'")

        if not flight_rows:
            # Last resort - find all tr elements and check which have data-rid
            all_trs = response.css('tr')
            logger.info(f"Found {len(all_trs)} total tr elements")
            flight_rows = [tr for tr in all_trs if tr.attrib.get('data-rid')]
            logger.info(f"Filtered to {len(flight_rows)} tr elements with data-rid attribute")

        # Count flights by filter reason
        filter_stats = {
            'total': len(flight_rows),
            'already_downloaded': 0,
            'below_min_points': 0,
            'will_follow': 0
        }

        for row in flight_rows:
            # Extract data from the row
            dsid = row.attrib.get('data-rid')

            # Check if already downloaded
            if dsid in self.downloaded_dsids:
                filter_stats['already_downloaded'] += 1
                logger.debug(f"Skipping already downloaded flight dsid={dsid}")
                continue

            # Extract date
            date_cell = row.xpath('.//td[@data-cn="date"]/text()').get()
            date = date_cell.strip().split()[0] if date_cell else "unknown"  # Split to remove visible-xs elements

            # Extract points - FILTER HERE before following links!
            points_cell = row.xpath('.//td[@data-cn="points"]/text()').get()
            points = None
            if points_cell:
                try:
                    points_text = points_cell.strip().split()[0]
                    points = float(points_text)
                except (ValueError, IndexError):
                    pass

            # Filter by min_points if specified - SKIP flights that don't meet threshold
            if self.min_points is not None:
                if points is None or points < self.min_points:
                    filter_stats['below_min_points'] += 1
                    logger.debug(f"Skipping flight {dsid} with {points} points (below threshold {self.min_points})")
                    continue

            # This flight will be followed
            filter_stats['will_follow'] += 1

            # Extract pilot name - it's in data-cn="name" on public pages
            pilot_cell = row.xpath('.//td[@data-cn="name"]//a[contains(@href, "flightbook.html")]/@title').get()
            if not pilot_cell:
                # Fallback: try getting text content
                pilot_cell = row.xpath('.//td[@data-cn="name"]//a[contains(@href, "flightbook.html")]/text()').get()
            pilot = pilot_cell.strip() if pilot_cell else "Unknown"

            # Airport - assume it's the airport we're searching for
            airport = f"Airport {self.airport_code}"

            # Get the flightinfo link to follow
            flightinfo_link = row.xpath('.//td[@data-cn="info"]//a[contains(@href, "flightinfo.html")]/@href').get()

            if flightinfo_link:
                flightinfo_url = response.urljoin(flightinfo_link.split('#')[0])

                logger.info(f"Following flightinfo link for dsId {dsid}, pilot {pilot}")
                yield scrapy.Request(
                    flightinfo_url,
                    callback=self.parse_flightinfo,
                    cookies={cookie['name']: cookie['value'] for cookie in self.cookies},
                    meta={
                        "dsid": dsid,
                        "year": self.year,
                        "airport": airport,
                        "points": points,
                        "date": date,
                        "pilot": pilot,
                    },
                )

        # Check if we might be missing rows due to lazy loading
        pagination_info = response.xpath('//text()[contains(., "items found") or contains(., "items")]').get()
        total_items = None
        if pagination_info:
            match = re.search(r'(\d+)\s+items?\s+found', pagination_info)
            if match:
                total_items = int(match.group(1))

        # Log summary
        logger.info("=" * 60)
        logger.info(f"PARSE SUMMARY for {self.airport_code} {self.year}:")
        logger.info(f"  Total rows found in DOM: {filter_stats['total']}")
        if total_items and total_items > filter_stats['total']:
            logger.warning(f"  ⚠️  Page shows {total_items} total items but only {filter_stats['total']} rows loaded in DOM")
            logger.warning(f"  ⚠️  This is due to virtual scrolling/lazy loading limitations")
            logger.warning(f"  ⚠️  {total_items - filter_stats['total']} flights may be missing")
        logger.info(f"  Already downloaded: {filter_stats['already_downloaded']}")
        logger.info(f"  Below min points ({self.min_points}): {filter_stats['below_min_points']}")
        logger.info(f"  Will follow flightinfo links: {filter_stats['will_follow']}")
        logger.info("=" * 60)

    def parse_flightinfo(self, response):
        """Parse flightinfo page to extract download link"""
        dsid = response.meta.get('dsid')
        year = response.meta.get('year')
        airport = response.meta.get('airport')
        points = response.meta.get('points')
        date = response.meta.get('date')
        pilot = response.meta.get('pilot')
        distance = response.meta.get('distance')
        speed = response.meta.get('speed')
        aircraft = response.meta.get('aircraft')

        logger.info(f"Parsing flightinfo for dsId {dsid}, pilot {pilot}")

        # Look for download link
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

                # Try to improve date if needed
                if date == "unknown":
                    date_patterns = [
                        r'(\d{4}-\d{2}-\d{2})',
                        r'(\d{2}\.\d{2}\.\d{4})',
                        r'(\d{1,2}/\d{1,2}/\d{4})',
                    ]
                    for pattern in date_patterns:
                        match = re.search(pattern, response.text[:5000])
                        if match:
                            date = match.group(1)
                            break

                logger.info(f"Found download URL for dsId {dsid}: flightId={flight_id}")

                # Sanitize pilot name for filename (remove invalid characters)
                safe_pilot = pilot.replace(' ', '_').replace('/', '-').replace('\\', '-')
                # Remove other potentially problematic characters
                safe_pilot = ''.join(c for c in safe_pilot if c.isalnum() or c in ('_', '-', '(', ')'))

                yield {
                    'flight_id': flight_id,
                    'download_url': download_url,
                    'date': date,
                    'year': year,
                    'filename': f"{year}_{safe_pilot}_{flight_id}.igc",
                    'dsid': dsid,
                    'referer': response.url,
                    'airport': airport,
                    'points': points,
                    'pilot': pilot,  # Include pilot name for public flights
                    'distance': distance,  # Distance in km from OLC
                    'speed': speed,  # Speed in km/h from OLC
                    'aircraft': aircraft,  # Aircraft type from OLC
                }
        else:
            logger.warning(f"No download link found on flightinfo page for dsId {dsid}")

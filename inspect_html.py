#!/usr/bin/env python3
"""Save flightbook HTML for inspection"""

from src.olc_downloader.config import Config
from src.olc_downloader.auth import OLCAuthenticator
import re

config = Config()
username, password = config.get_credentials()

auth = OLCAuthenticator()
print("Logging in...")
auth.login(username, password)
session = auth.get_session()

# Add browser headers
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
})

url = "https://www.onlinecontest.org/olc-3.0/gliding/flightbook.html?rt=olc&st=olcp&pi=52380&sp=2024"
print(f"Fetching: {url}")
response = session.get(url, timeout=120)

print(f"Status: {response.status_code}")
print(f"Length: {len(response.text)} chars")

# Save HTML
with open('/tmp/flightbook_2024.html', 'w') as f:
    f.write(response.text)

print("\nSaved to /tmp/flightbook_2024.html")

# Quick analysis
print("\nQuick analysis:")
print(f"Contains 'download.html': {'download.html' in response.text}")
print(f"Contains 'flightId': {'flightId' in response.text}")
print(f"Contains 'dsId': {'dsId' in response.text}")
print(f"Contains '.igc': {'.igc' in response.text.lower()}")

# Search for flight IDs
flight_ids = re.findall(r'flightId["\']?\s*[:=]\s*["\']?(-?\d+)', response.text)
ds_ids = re.findall(r'dsId["\']?\s*[:=]\s*["\']?(-?\d+)', response.text)
download_links = re.findall(r'href="([^"]*download[^"]*)"', response.text)

print(f"\nFound {len(set(flight_ids))} unique flight IDs")
print(f"Found {len(set(ds_ids))} unique dataset IDs")
print(f"Found {len(download_links)} download links")

if flight_ids:
    print(f"\nFirst 5 flight IDs: {list(set(flight_ids))[:5]}")
if ds_ids:
    print(f"First 5 dataset IDs: {list(set(ds_ids))[:5]}")
if download_links:
    print(f"\nFirst 3 download links:")
    for link in download_links[:3]:
        print(f"  {link}")

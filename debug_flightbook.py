#!/usr/bin/env python3
"""Debug script to examine the flightbook page"""

import sys
from bs4 import BeautifulSoup
from src.olc_downloader.config import Config
from src.olc_downloader.auth import OLCAuthenticator

def main():
    # Load credentials and login
    config = Config()
    username, password = config.get_credentials()

    auth = OLCAuthenticator()
    print("Logging in...")
    auth.login(username, password)
    print("Login successful!\n")

    session = auth.get_session()

    # Try the flightbook URL
    url = "https://www.onlinecontest.org/olc-3.0/gliding/flightbook.html?sp=2026&st=olcp&rt=olc&pi=52380"
    print(f"Fetching: {url}")
    response = session.get(url)
    print(f"Status: {response.status_code}\n")

    if response.status_code != 200:
        print("Failed to fetch flightbook page")
        return

    soup = BeautifulSoup(response.text, 'lxml')

    # Look for years
    print("Looking for year selectors...")
    year_selects = soup.find_all('select')
    for select in year_selects:
        name = select.get('name', 'unnamed')
        print(f"\nSelect element: name='{name}'")
        options = select.find_all('option')
        print(f"  Options: {[opt.get_text(strip=True) for opt in options[:10]]}")

    # Look for IGC links
    print("\n\nLooking for IGC download links...")
    igc_links = soup.find_all('a', href=lambda h: h and '.igc' in h.lower())
    print(f"Found {len(igc_links)} IGC links")

    for i, link in enumerate(igc_links[:5]):
        href = link.get('href')
        text = link.get_text(strip=True)
        print(f"  {i+1}. Text: '{text}' -> {href}")

    # Look for flight tables
    print("\n\nLooking for flight tables...")
    tables = soup.find_all('table')
    print(f"Found {len(tables)} tables")

    for i, table in enumerate(tables[:3]):
        print(f"\nTable {i+1}:")
        rows = table.find_all('tr')[:5]
        for row in rows:
            cells = [cell.get_text(strip=True) for cell in row.find_all(['td', 'th'])]
            print(f"  {cells}")

    # Save the HTML for inspection
    with open('/tmp/flightbook.html', 'w') as f:
        f.write(response.text)
    print("\n\nSaved full HTML to /tmp/flightbook.html for inspection")

if __name__ == '__main__':
    main()

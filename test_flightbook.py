#!/usr/bin/env python3
"""Test script to examine flightbook page with correct URL"""

from bs4 import BeautifulSoup
import re
from src.olc_downloader.config import Config
from src.olc_downloader.auth import OLCAuthenticator

def main():
    config = Config()
    username, password = config.get_credentials()

    auth = OLCAuthenticator()
    print("Logging in...")
    auth.login(username, password)
    session = auth.get_session()

    # The correct flightbook URL pattern (we need to discover pilot ID)
    # For now, try to access the main page and extract pilot ID

    print("\nFetching main gliding page to find pilot ID...")
    response = session.get("https://www.onlinecontest.org/olc-3.0/gliding/index.html")

    # Look for pilot ID in the page
    pilot_id_match = re.search(r'pi=(\d+)', response.text)
    if pilot_id_match:
        pilot_id = pilot_id_match.group(1)
        print(f"Found pilot ID: {pilot_id}")

        # Try different years
        for year in [2026, 2025, 2024, 2023]:
            url = f"https://www.onlinecontest.org/olc-3.0/gliding/flightbook.html?rt=olc&st=olcp&pi={pilot_id}&sp={year}"
            print(f"\nTrying year {year}: {url}")

            try:
                response = session.get(url, timeout=15)
                print(f"Status: {response.status_code}")

                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'lxml')

                    # Look for flight links (flightinfo or download)
                    flight_links = soup.find_all('a', href=re.compile(r'flightinfo|download'))
                    print(f"Found {len(flight_links)} flight links")

                    # Look for dsId or flightId
                    dsid_matches = re.findall(r'dsId=(-?\d+)', response.text)
                    flightid_matches = re.findall(r'flightId=(-?\d+)', response.text)

                    print(f"Found {len(set(dsid_matches))} unique dsIds")
                    print(f"Found {len(set(flightid_matches))} unique flightIds")

                    if len(flight_links) > 0:
                        print("\nFirst 3 flight links:")
                        for link in flight_links[:3]:
                            href = link.get('href')
                            text = link.get_text(strip=True)
                            print(f"  {text}: {href}")

                    if len(set(dsid_matches)) > 0:
                        print(f"\nFirst 3 dsIds: {list(set(dsid_matches))[:3]}")
                    if len(set(flightid_matches)) > 0:
                        print(f"First 3 flightIds: {list(set(flightid_matches))[:3]}")

                    # If we found flights, stop here
                    if len(flight_links) > 0 or len(dsid_matches) > 0:
                        print(f"\n✓ Year {year} has flights!")
                        break

            except Exception as e:
                print(f"Error: {e}")
    else:
        print("Could not find pilot ID in page")

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Test OLC server accessibility with different settings"""

import requests
import time
from src.olc_downloader.config import Config
from src.olc_downloader.auth import OLCAuthenticator

def test_with_longer_timeout():
    """Test with much longer timeout"""
    config = Config()
    username, password = config.get_credentials()

    auth = OLCAuthenticator()
    print("Logging in...")
    auth.login(username, password)
    session = auth.get_session()

    # Add more browser-like headers
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
    })

    # Test URL from user's example
    test_url = "https://www.onlinecontest.org/olc-3.0/gliding/flightbook.html?rt=olc&st=olcp&pi=52380&sp=2024"

    print(f"\nTrying {test_url}")
    print("Waiting up to 120 seconds...")

    try:
        # Try with very long timeout
        response = session.get(test_url, timeout=120)
        print(f"✓ Success! Status: {response.status_code}")
        print(f"Response length: {len(response.text)} chars")

        # Check for key content
        if 'flightId' in response.text or 'dsId' in response.text:
            print("✓ Found flight data in response!")

            # Count potential flights
            import re
            flight_ids = re.findall(r'flightId=(-?\d+)', response.text)
            ds_ids = re.findall(r'dsId=(-?\d+)', response.text)
            print(f"Found {len(set(flight_ids))} flight IDs")
            print(f"Found {len(set(ds_ids))} dataset IDs")

            if flight_ids:
                print(f"Sample flight ID: {flight_ids[0]}")

        return True

    except requests.Timeout:
        print("✗ Still timed out after 120 seconds")
        return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False

def test_main_pages():
    """Test if other pages work"""
    config = Config()
    username, password = config.get_credentials()

    auth = OLCAuthenticator()
    print("\nTesting main pages accessibility...")
    auth.login(username, password)
    session = auth.get_session()

    test_urls = [
        "https://www.onlinecontest.org/olc-3.0/gliding/index.html",
        "https://www.onlinecontest.org/olc-3.0/gliding/daily.html?st=olc&rt=olc&c=C0&sc=&sp=2024",
    ]

    for url in test_urls:
        try:
            print(f"\nTrying: {url}")
            response = session.get(url, timeout=15)
            print(f"Status: {response.status_code}, Length: {len(response.text)}")
        except Exception as e:
            print(f"Failed: {e}")

if __name__ == '__main__':
    print("=" * 60)
    print("OLC Server Diagnostic Test")
    print("=" * 60)

    # Test main pages first
    test_main_pages()

    print("\n" + "=" * 60)
    print("Testing Flightbook Page (this may take 2+ minutes)")
    print("=" * 60)

    # Test flightbook with longer timeout
    success = test_with_longer_timeout()

    if not success:
        print("\n" + "=" * 60)
        print("CONCLUSION")
        print("=" * 60)
        print("The OLC flightbook pages are currently timing out.")
        print("This is a server-side issue - the pages are too slow to load.")
        print("\nPossible solutions:")
        print("1. Try again later when server is less busy")
        print("2. Try accessing the page in a browser first")
        print("3. Contact OLC support about server performance")
        print("4. Consider using browser automation (Selenium) instead")

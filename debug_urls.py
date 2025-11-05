#!/usr/bin/env python3
"""Debug script to find the correct flight history URL"""

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

    # Try to fetch main gliding page
    print("Fetching main gliding page after login...")
    response = session.get("https://www.onlinecontest.org/olc-3.0/gliding/index.html")
    print(f"Status: {response.status_code}\n")

    soup = BeautifulSoup(response.text, 'lxml')

    # Look for user menu or profile links
    print("Looking for user/profile related links...")
    user_links = []

    for link in soup.find_all('a', href=True):
        href = link.get('href')
        text = link.get_text(strip=True)

        # Look for keywords that might indicate personal/profile pages
        keywords = ['flight', 'pilot', 'profile', 'book', 'my', 'user', 'account',
                   'flug', 'historie', 'mein', 'profil']

        if any(keyword in href.lower() or keyword in text.lower() for keyword in keywords):
            if href not in [ul[0] for ul in user_links]:  # Avoid duplicates
                user_links.append((href, text))

    print(f"\nFound {len(user_links)} potentially relevant links:\n")
    for href, text in user_links[:30]:  # Show first 30
        if not href.startswith('http'):
            href = f"https://www.onlinecontest.org/{href.lstrip('/')}"
        print(f"  Text: '{text}' -> {href}")

    # Try to find username in the page
    print("\n\nLooking for logged-in user indicators...")

    # Look for logout or username displays
    logout_links = soup.find_all('a', href=lambda h: h and 'logout' in h.lower())
    print(f"Found {len(logout_links)} logout links")

    user_divs = soup.find_all(class_=lambda c: c and ('user' in c.lower() or 'pilot' in c.lower()))
    print(f"Found {len(user_divs)} user/pilot divs")

    # Check for common navigation patterns
    print("\n\nChecking navigation menus...")
    nav_menus = soup.find_all(['nav', 'ul', 'div'], class_=lambda c: c and 'nav' in c.lower())

    for i, nav in enumerate(nav_menus[:5]):
        print(f"\nNav menu {i+1}:")
        links = nav.find_all('a', href=True, limit=10)
        for link in links:
            print(f"  {link.get_text(strip=True)} -> {link.get('href')}")

if __name__ == '__main__':
    main()

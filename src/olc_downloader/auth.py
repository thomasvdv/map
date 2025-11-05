"""Authentication module for OLC website"""

import requests
from bs4 import BeautifulSoup
from typing import Optional
import logging
from .exceptions import AuthenticationError

logger = logging.getLogger(__name__)


class OLCAuthenticator:
    """Handles authentication with onlinecontest.org"""

    BASE_URL = "https://www.onlinecontest.org"
    LOGIN_URL = f"{BASE_URL}/olc-3.0/secure/login.html"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        self.authenticated = False
        self._username = None
        self._password = None

    def login(self, username: str, password: str) -> bool:
        """
        Login to OLC website

        Args:
            username: OLC username
            password: OLC password

        Returns:
            bool: True if login successful

        Raises:
            AuthenticationError: If login fails
        """
        # Store credentials for session refresh
        self._username = username
        self._password = password

        try:
            # First, get the login page to extract any CSRF tokens or form fields
            logger.info("Fetching login page...")
            response = self.session.get(self.LOGIN_URL)
            response.raise_for_status()

            # Parse the login form
            soup = BeautifulSoup(response.text, 'lxml')
            login_form = soup.find('form')

            if not login_form:
                raise AuthenticationError("Could not find login form on page")

            # Extract form action and prepare login data
            form_action = login_form.get('action', self.LOGIN_URL)
            if not form_action.startswith('http'):
                form_action = f"{self.BASE_URL}/{form_action.lstrip('/')}"

            # Build login payload with correct field names
            login_data = {
                '_ident_': username,
                '_name__': password,
                'ok_par.x': '1',  # Submit button value
            }

            # Add any hidden fields from the form
            for hidden in login_form.find_all('input', type='hidden'):
                name = hidden.get('name')
                value = hidden.get('value', '')
                if name:
                    login_data[name] = value

            logger.info("Attempting login...")
            response = self.session.post(form_action, data=login_data, allow_redirects=True)
            response.raise_for_status()

            # Check if login was successful
            # Look for indicators of successful login (e.g., user menu, logout link)
            if 'logout' in response.text.lower() or 'abmelden' in response.text.lower():
                self.authenticated = True
                logger.info("Login successful!")
                return True
            else:
                raise AuthenticationError("Login failed - invalid credentials or unexpected response")

        except requests.RequestException as e:
            raise AuthenticationError(f"Network error during login: {e}")

    def is_authenticated(self) -> bool:
        """Check if currently authenticated"""
        return self.authenticated

    def get_session(self) -> requests.Session:
        """Get the authenticated session"""
        if not self.authenticated:
            raise AuthenticationError("Not authenticated. Please login first.")
        return self.session

    def refresh_session(self) -> bool:
        """
        Refresh the session by re-authenticating

        Returns:
            bool: True if refresh successful

        Raises:
            AuthenticationError: If refresh fails or no credentials stored
        """
        if not self._username or not self._password:
            raise AuthenticationError("Cannot refresh session - no credentials stored")

        logger.info("Refreshing session...")

        # Create a new session (old one is expired)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        })
        self.authenticated = False

        # Re-login with stored credentials
        return self.login(self._username, self._password)

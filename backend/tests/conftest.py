"""Test configuration.

Sets the minimum required environment variables so the app can start
under pytest without a real .env file. These values are only used in
the test environment and are never committed as production credentials.
"""

import os

# Must be set before app.main is imported so Settings() picks them up.
os.environ.setdefault("KOI_AUTH_PASSWORD", "test-password-for-pytest")
os.environ.setdefault("KOI_AUTH_SESSION_SECRET", "test-session-secret-for-pytest-32chars!!")

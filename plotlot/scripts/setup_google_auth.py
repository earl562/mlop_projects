#!/usr/bin/env python3
"""One-time Google OAuth setup — get a refresh_token for PlotLot.

Uses the same Google OAuth client as the Gemini CLI (already installed).
Just run this script, click "Allow" in the browser, and you're done.

Usage:
  python scripts/setup_google_auth.py

The script will automatically update your .env file with the credentials.
"""

import http.server
import json
import os
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

# Google OAuth client — loaded from environment or .env file.
# Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your .env before running.
OAUTH_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

REDIRECT_PORT = 8090
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"
TOKEN_URL = "https://oauth2.googleapis.com/token"

# Will be set by the callback handler
_auth_code: str | None = None
_server_done = threading.Event()


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    """Handles the OAuth redirect and extracts the auth code."""

    def do_GET(self):
        global _auth_code
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h2>Success! You can close this tab.</h2>"
                             b"<p>PlotLot has received your authorization. "
                             b"Go back to the terminal.</p></body></html>")
        else:
            error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(f"<html><body><h2>Error: {error}</h2></body></html>".encode())

        _server_done.set()

    def log_message(self, format, *args):
        pass  # Suppress server logs


def update_env_file(refresh_token: str):
    """Add Google credentials to .env file."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        print(f"Warning: {env_path} not found. Create it from .env.example first.")
        return False

    content = env_path.read_text()

    # Check if Google creds already exist
    if "GOOGLE_REFRESH_TOKEN=" in content and "GOOGLE_REFRESH_TOKEN=\n" not in content and "GOOGLE_REFRESH_TOKEN=$" not in content:
        print("Google credentials already in .env — updating...")
        lines = content.split("\n")
        new_lines = []
        for line in lines:
            if line.startswith("GOOGLE_CLIENT_ID="):
                new_lines.append(f"GOOGLE_CLIENT_ID={OAUTH_CLIENT_ID}")
            elif line.startswith("GOOGLE_CLIENT_SECRET="):
                new_lines.append(f"GOOGLE_CLIENT_SECRET={OAUTH_CLIENT_SECRET}")
            elif line.startswith("GOOGLE_REFRESH_TOKEN="):
                new_lines.append(f"GOOGLE_REFRESH_TOKEN={refresh_token}")
            else:
                new_lines.append(line)
        env_path.write_text("\n".join(new_lines))
    else:
        # Append
        block = (
            "\n# Google Workspace (Sheets/Docs creation — auto-configured)\n"
            f"GOOGLE_CLIENT_ID={OAUTH_CLIENT_ID}\n"
            f"GOOGLE_CLIENT_SECRET={OAUTH_CLIENT_SECRET}\n"
            f"GOOGLE_REFRESH_TOKEN={refresh_token}\n"
        )
        env_path.write_text(content.rstrip() + block)

    print(f"Updated {env_path}")
    return True


def main():
    print("PlotLot Google Workspace Setup")
    print("=" * 40)

    if not OAUTH_CLIENT_ID or not OAUTH_CLIENT_SECRET:
        print("Error: GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set")
        print("in your .env file before running this script.")
        sys.exit(1)

    print("This will open your browser to authorize PlotLot to create")
    print("Google Sheets and Docs on your behalf.\n")

    # Build the consent URL
    scope_str = " ".join(SCOPES)
    auth_params = urllib.parse.urlencode({
        "client_id": OAUTH_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": scope_str,
        "access_type": "offline",
        "prompt": "consent",
    })
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{auth_params}"

    # Start local server to catch the redirect
    server = http.server.HTTPServer(("localhost", REDIRECT_PORT), OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    print("Opening browser for Google login...")
    print(f"If it doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Wait for the callback
    print("Waiting for you to click 'Allow'...")
    _server_done.wait(timeout=120)
    server.server_close()

    if not _auth_code:
        print("\nError: Did not receive authorization. Try again.")
        sys.exit(1)

    print("Got authorization! Getting tokens...")

    # Exchange auth code for tokens
    token_data = urllib.parse.urlencode({
        "code": _auth_code,
        "client_id": OAUTH_CLIENT_ID,
        "client_secret": OAUTH_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=token_data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req) as resp:
            tokens = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"\nToken exchange failed: {error_body}")
        sys.exit(1)

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("\nError: No refresh_token in response.")
        print(f"Response: {json.dumps(tokens, indent=2)}")
        sys.exit(1)

    # Auto-update .env
    if update_env_file(refresh_token):
        print("\nDone! Your .env is configured.")
        print("Restart the backend to pick up the new credentials.")
    else:
        print(f"\nManually add to .env:")
        print(f"GOOGLE_CLIENT_ID={OAUTH_CLIENT_ID}")
        print(f"GOOGLE_CLIENT_SECRET={OAUTH_CLIENT_SECRET}")
        print(f"GOOGLE_REFRESH_TOKEN={refresh_token}")

    print("\nPlotLot can now create Google Sheets and Docs!")


if __name__ == "__main__":
    main()

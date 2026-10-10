"""
SafeRouteAI - Dashboard Launcher
Author: SafeRouteAI Team

Convenient Python launcher script for the Streamlit dashboard.
Usage:
    python scripts/run_app.py
"""

import os
import subprocess
import sys


def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app_file = os.path.join(base_dir, "app.py")

    if not os.path.exists(app_file):
        print(f"Error: app.py not found at {app_file}", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print("SafeRouteAI - Launching Multi-Hazard Routing Dashboard")
    print("Study Area: Daraganj, Prayagraj, India")
    print("=" * 60)

    port = os.environ.get("PORT", "8501")
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = sys.argv[1]

    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        app_file,
        "--server.headless=true",
        f"--server.port={port}",
    ]

    try:
        subprocess.run(cmd, cwd=base_dir, check=True)
    except KeyboardInterrupt:
        print("\nSafeRouteAI Dashboard stopped.")


if __name__ == "__main__":
    main()

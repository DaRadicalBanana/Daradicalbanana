#!/usr/bin/env python3
"""Serve the app on your local network so you can open it on your phone.

Run this on your computer (e.g. your Mac), with your phone on the SAME Wi-Fi:

    python scripts/serve.py
    # or choose a port:  PORT=9000 python scripts/serve.py

It binds to 0.0.0.0, prints the URL to type on your phone, and (if the optional
`qrcode` package is installed) a QR code you can just point your camera at.

Notes
- First run, macOS may ask "allow incoming network connections?" — click Allow.
- This serves over plain HTTP on your LAN; fine for personal use at home.
- For access when you're NOT on the same Wi-Fi, see the README (cloudflared
  tunnel) — that's optional and not required for same-network use.
"""
from __future__ import annotations

import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def lan_ip() -> str:
    """Best-effort primary LAN IPv4 address (no packets are actually sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))  # picks the default route's interface
        return s.getsockname()[0]
    except OSError:
        try:
            return socket.gethostbyname(socket.gethostname())
        except OSError:
            return "127.0.0.1"
    finally:
        s.close()


def print_access(port: int) -> str:
    ip = lan_ip()
    url = f"http://{ip}:{port}"
    line = "=" * 56
    print(f"\n{line}")
    print("  Crunchyroll Weekly Schedule — open this on your phone:")
    print(f"\n     {url}")
    print(f"\n  (on this computer: http://localhost:{port} )")
    print(line)
    _print_qr(url)
    print("  Phone + computer must be on the same Wi-Fi.")
    print("  Stop the server with Ctrl-C.\n")
    return url


def _print_qr(url: str) -> None:
    try:
        import qrcode  # optional dependency
    except ImportError:
        print("\n  (install `qrcode` to show a scannable QR here: pip install qrcode)\n")
        return
    qr = qrcode.QRCode(border=2)
    qr.add_data(url)
    qr.make(fit=True)
    print()
    qr.print_ascii(invert=True)  # invert renders well on dark terminals


def main() -> int:
    port = int(os.getenv("PORT", "8000"))
    print_access(port)
    try:
        import uvicorn
    except ImportError:
        print("uvicorn is not installed. Run: pip install -r requirements.txt", file=sys.stderr)
        return 1
    # import string form so uvicorn can manage the app lifecycle cleanly
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

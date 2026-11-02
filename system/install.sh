#!/usr/bin/env bash
# Installs the head unit on a Raspberry Pi: builds the programs, creates the
# bean user, and installs the splash, config and systemd services.
# Safe to run again to update. Usage: system/install.sh [--sim]
#   --sim  also start the fake core at boot (for desk testing without the car)
set -euo pipefail

if [ "$EUID" -eq 0 ]; then
    echo "Run this as your normal user. It uses sudo where it needs to." >&2
    exit 1
fi

if ! command -v cargo >/dev/null; then
    echo "cargo not found. Install Rust first: https://rustup.rs" >&2
    exit 1
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHARE=/usr/local/share/bean-headunit
CONFIG=/etc/bean-headunit/bean.env
UNITS=/etc/systemd/system

WITH_SIM=no
if [ "${1:-}" = "--sim" ]; then WITH_SIM=yes; fi

echo "Building..."
cargo build --release -p bean-ui -p bean-sim --manifest-path "$REPO/Cargo.toml"

echo "Creating the bean user..."
if ! id bean &>/dev/null; then
    sudo useradd --system --no-create-home --shell /usr/sbin/nologin --groups video,input bean
fi

echo "Installing programs..."
sudo install -m 755 "$REPO/target/release/bean-ui" "$REPO/target/release/bean-sim" /usr/local/bin/

echo "Installing the splash..."
sudo install -D -m 644 "$REPO/splash/splash.py" "$SHARE/splash/splash.py"
sudo rm -rf "$SHARE/splash/frames"
sudo cp -r "$REPO/splash/frames" "$SHARE/splash/"

echo "Installing config..."
if [ ! -f "$CONFIG" ]; then
    sudo install -D -m 644 "$REPO/system/bean.env.example" "$CONFIG"
    echo "  Created $CONFIG with default settings. Edit it to set your title and screen scale."
else
    echo "  Keeping your existing $CONFIG"
fi

echo "Installing services..."
sudo install -m 644 "$REPO/splash/bean-splash.service" "$REPO/system/bean-ui.service" \
    "$REPO/system/bean-sim.service" "$UNITS/"
sudo systemctl daemon-reload
sudo systemctl enable bean-splash bean-ui
if [ "$WITH_SIM" = yes ]; then
    sudo systemctl enable bean-sim
else
    sudo systemctl disable --now bean-sim
fi

if command -v etckeeper >/dev/null; then
    sudo etckeeper commit "Install or update bean-headunit" || true
fi

echo "Done. Reboot, or run: sudo systemctl restart bean-ui"
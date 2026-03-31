# Super Productivity Today Overlay (Desktop)

Small always‑on‑top desktop overlay for  
[Super Productivity](https://github.com/johannesjo/super-productivity).

It shows:

- current **workspace name** (via `wmctrl -d`)
- only **Today** tasks from Super Productivity
- a tiny GTK window that hugs the **bottom‑right** of your primary monitor
- dynamic height (grows/shrinks with Today list)

The main app (and your tasks) stay inside Super Productivity — this is just a
read‑only Today panel for your desktop.

## Screenshots

## Screenshots

<p align="center">
  <img src="screenshots/overlay-desktop-1.png"
       alt="Super Productivity Today Overlayed apps /shrinked"
       width="350"
       style="margin-right: 12px;">
  <img src="screenshots/overlay-desktop-2.jpeg"
       alt="Super Productivity Today Overlayed apps /grown"
       width="350"
       style="margin-left: 12px;">
</p>



## Requirements

- Linux + X11 (tested on Linux Mint Cinnamon)
- Python 3
- GTK 3 bindings:

```bash
sudo apt install wmctrl python3-gi python3-gi-cairo gir1.2-gtk-3.0
```

- Super Productivity with **Local REST API** enabled:
  - Settings → **Misc** → enable **Local REST API (desktop only)**

## Files in this repo

- `today-overlay.py` — main GTK app
- `config.example.json` — example config (copied to `~/.config/super-today-overlay/config.json`)
- `start-super-today-overlay.sh` — helper to start in background + PID file
- `stop-super-today-overlay.sh` — helper to stop cleanly
- `super-today-overlay-guide.md` — longer usage / architecture notes

## Install

Clone the repo and run:

```bash
mkdir -p ~/.config/super-today-overlay
cp config.example.json ~/.config/super-today-overlay/config.json
cp today-overlay.py ~/.config/super-today-overlay/today-overlay.py
chmod +x start-super-today-overlay.sh stop-super-today-overlay.sh
```

Optional: install the icon to integrate with your theme:

```bash
mkdir -p ~/.local/share/icons/hicolor/scalable/apps
cp super-today-overlay.svg ~/.local/share/icons/hicolor/scalable/apps/super-today-overlay.svg
```

*(If you don’t have the SVG yet, you can skip this step — the app still works.)*

## Run

From the repo folder:

```bash
./start-super-today-overlay.sh
```

That script:

- stops any previous overlay instance
- runs `~/.config/super-today-overlay/today-overlay.py` in the background
- writes a PID file to `~/.config/super-today-overlay/overlay.pid`
- logs to `/tmp/super-today-overlay.log`

To stop:

```bash
./stop-super-today-overlay.sh
```

## Autostart (optional)

Create an autostart entry (example for GNOME/Cinnamon):

```bash
cat > ~/.config/autostart/super-today-overlay.desktop << 'EOF'
[Desktop Entry]
Version=1.0
Type=Application
Name=Super Productivity Today Overlay
Comment=Workspace-aware Today panel for Super Productivity
Exec=/full/path/to/this/repo/start-super-today-overlay.sh
Terminal=false
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=5
Hidden=false
EOF
```

Then log out / log back in.

## How it finds Today tasks

The overlay talks to Super Productivity’s **local REST API** on
`http://127.0.0.1:3876` and reads:

- `GET /tasks`
- `GET /status`
- `GET /projects`
- `GET /tags`

The **Today** list is driven by the special `TODAY` tag’s `taskIds` array
instead of guessing based on task fields, which matches the app’s own logic.

If the API is disabled or not reachable, the overlay can fall back to the
backup JSONs under `~/.config/superProductivity/backups/` (see the longer
guide for details).



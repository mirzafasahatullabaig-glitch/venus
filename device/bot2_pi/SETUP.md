# Bot 2 (Raspberry Pi) — setup, top to bottom

This folder is self-contained. Nothing here needs the laptop's Python environment
or any file from `brain/`. Copy this folder to the Pi and run the commands below
in order. `<LAPTOP_TAILNET>` is the laptop's tailnet address (e.g. `100.76.45.98`)
and `<API_KEY>` is the `api_key` from the laptop's `brain/config.toml`.

## 1. Install Tailscale and sign in (on the Pi)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up          # follow the login URL it prints
tailscale ip -4            # note the Pi's tailnet IP
```

Confirm the Pi can reach the laptop's brain over the tailnet:

```bash
curl http://<LAPTOP_TAILNET>:8080/health        # expect {"status":"ok"}
```

## 2. Copy this folder onto the Pi

From your laptop, copy just this folder (no `brain/` needed):

```bash
scp -r device/bot2_pi pi@<PI_TAILNET>:/home/pi/bot2_pi
```

(Or `git clone` the repo on the Pi and use only `device/bot2_pi/`.)

## 3. Install the Pi's dependency

```bash
cd /home/pi/bot2_pi
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 4. Configure

```bash
cp config.example.json config.json
nano config.json     # set brain_url to http://<LAPTOP_TAILNET>:8080 and api_key to <API_KEY>
```

## 5. Run

```bash
.venv/bin/python relay.py
```

You should see `watching live runs`. Start a run from the laptop cockpit and this
Pi prints **Bot 2's** turns. It also serves the ESP32 at `http://<PI_TAILNET or LAN IP>:8100`:

- `GET /latest` — the newest **Bot 1** turn (the ESP32 polls this and prints it to Serial).
- `POST /line` with `{"text": "..."}` — assigns that line as a new task.

Quick local checks (from the Pi or another machine on its LAN):

```bash
curl http://localhost:8100/health
curl http://localhost:8100/latest
curl -X POST http://localhost:8100/line -H 'Content-Type: application/json' -d '{"text":"say hello"}'
```

## 6. Run on boot (optional)

```bash
sudo cp venus-bot2.service /etc/systemd/system/
# edit User/paths in the unit if you didn't use /home/pi/bot2_pi
sudo systemctl daemon-reload
sudo systemctl enable --now venus-bot2
journalctl -u venus-bot2 -f      # watch its logs
```

## Notes

- The ESP32 reaches this Pi over your **local WiFi** (point the ESP32's
  `RELAY_HOST` in `secrets.h` at the Pi's LAN IP, port 8100). The Pi reaches the
  laptop over the **tailnet**. The ESP32 never needs Tailscale.
- Backup path: if the tailnet is unavailable, expose the laptop app with
  Tailscale **Funnel** and set `brain_url` to that public URL.

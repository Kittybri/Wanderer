# Oracle Always Free deployment for Scaramouche + Wanderer

This folder prepares the bots to run off Railway on a single Oracle Cloud Always Free Linux VM.

## Why this setup

- Website stays on GitHub Pages
- Discord bots move off Railway
- Video rendering can stay on your local worker and tunnel, so the Oracle VM only has to run the bots
- Oracle Cloud advertises Always Free compute resources that are a better fit than Railway's post-trial free limits

Official reference:

- [Oracle Cloud Free Tier](https://www.oracle.com/cloud/free/)

## What this deployment runs

- `scaramouche-bot.service`
- `wanderer-bot.service`

These are two systemd services on the same VM.

## High-level steps

1. Create an Oracle Cloud Always Free Linux VM.
2. Copy your bot code onto the VM.
3. Run `setup_oracle_free.sh`.
4. Fill in the two env files:
   - `/opt/scara-wanderer-bots/deploy/oracle-free/scaramouche.env`
   - `/opt/scara-wanderer-bots/deploy/oracle-free/wanderer.env`
5. Enable the services.

## Recommended VM layout

Repository path:

```text
/opt/scara-wanderer-bots
```

Python virtualenv:

```text
/opt/scara-wanderer-bots/.venv
```

## Install

On the VM:

```bash
cd /opt
git clone https://github.com/Kittybri/scaramouche.git scara-wanderer-bots
cd /opt/scara-wanderer-bots
bash deploy/oracle-free/setup_oracle_free.sh
```

If you keep the combined working tree elsewhere, adjust the path in the systemd unit files before enabling them.

On Oracle Linux, the default SSH user is typically `opc`, and the setup script now supports both `dnf` and `apt-get`.

## Environment files

Copy the examples:

```bash
cp deploy/oracle-free/scaramouche.env.example deploy/oracle-free/scaramouche.env
cp deploy/oracle-free/wanderer.env.example deploy/oracle-free/wanderer.env
```

Then fill in the real values.

## Enable services

```bash
sudo cp deploy/oracle-free/scaramouche-bot.service /etc/systemd/system/
sudo cp deploy/oracle-free/wanderer-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now scaramouche-bot
sudo systemctl enable --now wanderer-bot
```

## Check status

```bash
sudo systemctl status scaramouche-bot
sudo systemctl status wanderer-bot
journalctl -u scaramouche-bot -f
journalctl -u wanderer-bot -f
```

## Notes

- These services do **not** run the Blender video renderer on Oracle.
- Keep your local render worker for `!teachvideo`, `!weathervideo`, and future Google Docs remote worker usage if needed.
- Set `VIDEO_RENDER_MODE=remote` and point the bots to your worker tunnel URL.

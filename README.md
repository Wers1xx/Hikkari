<div align="center">
  <h1>✨ Hikkari Userbot</h1>
  <p><b>Modular Telegram userbot</b> — fast, secure, developer-friendly</p>
  <p>
    <a href="https://github.com/Wers1xx/Hikkari"><img src="https://img.shields.io/github/stars/Wers1xx/Hikkari" alt="Stars"></a>
    <a href="https://github.com/Wers1xx/Hikkari/blob/master/LICENSE"><img src="https://img.shields.io/github/license/Wers1xx/Hikkari" alt="License"></a>
    <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python">
  </p>
</div>

## ⚠️ Security

- Install modules **only** from sources you trust
- Treat `.terminal` / `.eval` as root access to your machine
- Never share session files, bot tokens, or database dumps
- Project blacklist: accounts listed in `assets/BlackList.txt` cannot run Hikkari

## 🚀 Installation

### VPS / VDS (Ubuntu / Debian)

```bash
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip && \
git clone https://github.com/Wers1xx/Hikkari && \
cd Hikkari && \
python3 -m venv .venv && source .venv/bin/activate && \
pip install -U pip && pip install -r requirements.txt && \
python3 -m hikkari
```

Useful flags:

| Flag | Meaning |
|------|---------|
| `--root` | Allow running as root |
| `--no-web` | Console-only auth (no web UI) |
| `--proxy-pass` | SSH tunnel helper for web UI on VPS |

### Termux (Android)

```bash
pkg update && pkg install -y git python && \
git clone https://github.com/Wers1xx/Hikkari && cd Hikkari && \
pip install -r requirements.txt && \
python -m hikkari --no-web
```

### Docker

```bash
git clone https://github.com/Wers1xx/Hikkari && cd Hikkari
docker build -t hikkari .
docker run -d --name Hikkari --restart unless-stopped \
  -v "$(pwd)":/data/Hikkari hikkari
```

### Official hostings

| Host | Bot |
|------|-----|
| **WersHost** | [@WersHost_bot](https://t.me/WersHost_bot) |
| **UserBotHost** | [@UserBotHost_bot](https://t.me/UserBotHost_bot) |

After install, open the link shown in the terminal (or bot) and log in with Telegram.

## 📚 Commands

| Command | Description |
|---------|-------------|
| `.help` | Modules & commands |
| `.find <query>` | Search modules (HikkariFind, paginated) |
| `.dlmod <name\|url>` | Install module |
| `.update` | Update userbot |
| `.cfg` | Inline config |
| `.backupall` | Full backup |

## 🔗 Links

- GitHub: https://github.com/Wers1xx/Hikkari
- Channel: https://t.me/Hikkari_Channel
- Support: https://t.me/Hikkari_talks

## 📄 License

GNU AGPLv3

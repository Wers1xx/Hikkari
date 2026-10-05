<div align="center">
  <h1>✨ Hikkari</h1>
  <p>Modular Telegram userbot</p>
  <p>
    <a href="https://github.com/Wers1xx/Hikkari"><img src="https://img.shields.io/github/stars/Wers1xx/Hikkari" alt="Stars"></a>
    <a href="https://github.com/Wers1xx/Hikkari/blob/master/LICENSE"><img src="https://img.shields.io/github/license/Wers1xx/Hikkari" alt="License"></a>
  </p>
</div>

## Security

- Install modules only from trusted sources / official repos
- Be careful with `.terminal`, `.eval` and similar commands

## Install (VPS / Ubuntu)

```bash
sudo apt update && sudo apt install -y git python3 python3-venv && \
git clone https://github.com/Wers1xx/Hikkari && \
cd Hikkari && \
python3 -m venv .venv && source .venv/bin/activate && \
pip install -r requirements.txt && \
python3 -m hikkari
```

Root: add `--root` if needed.

## Docker

```bash
git clone https://github.com/Wers1xx/Hikkari && cd Hikkari
docker build -t hikkari .
docker run -d --name Hikkari --restart unless-stopped -v "$(pwd)":/data/Hikkari hikkari
```

## Useful commands

| Command | Description |
|--------|-------------|
| `.help` | Modules & commands |
| `.find <query>` | Search modules in repos |
| `.dlmod <name\|url>` | Install module |
| `.update` | Update userbot |
| `.rollback N` / `.rollback X.Y.Z` | Rollback commits or version |
| `.backupall` | Full backup |

## Links

- Repo: https://github.com/Wers1xx/Hikkari
- Channel: https://t.me/Hikkari_Channel
- Support: https://t.me/Hikkari_talks

## License

GNU AGPLv3

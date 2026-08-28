# hidebot — YourCloudBot

A Telegram bot that turns a chat with itself into private storage. Anything you
forward to it — text, photos, voice notes, video — lands in a named **room**.
Rooms are public (plain folders) or private: a private room needs an access key,
and without that key you cannot even tell whether it exists.

Live bot: [@your_cloudbot](https://t.me/your_cloudbot).
The bot speaks Russian; the code and docs are in English.
The original product description (RU) is kept at [docs/README.ru.md](docs/README.ru.md).

## Features

- **Rooms** — every message is filed into a room you name; rooms are listed from
  the main menu or opened by typing the name.
- **Private rooms** — protected by an access key. A wrong key is
  indistinguishable from a room that does not exist.
- **Any content type** — text, images, audio messages, video, forwards from
  other chats.
- **Edit in place** — forward a stored message back with a `.` to delete it;
  rename, re-key or flip a room between public and private from Settings.
- **Chat hygiene** — clears its own leftover messages, or the whole history.
- **Admin panel** — `/admin` for the username listed in `ADMIN_USERNAME`.

## How it is built

The bot is a small **scenario engine** rather than a pile of handlers:
`base_scenario.py` defines a step, `scenarios.py` declares the flows (creating a
room, entering a key, uploading content), and `scenario_runner.py` walks a user
through them. State and content live in PostgreSQL (`db.py`).
`bot_mock_driver.py` fakes the Telegram API so the flows can be tested without
a network.

```
main.py                  # entry point
app/
  bot.py handlers.py     # Telegram wiring (pyTelegramBotAPI)
  base_scenario.py scenarios.py scenario_runner.py   # the flow engine
  db.py                  # PostgreSQL storage
  config.py constants.py utils.py bot_utils.py
  bot_mock_driver.py     # fake Telegram driver used by the tests
tests/                   # pytest: scenarios, admin panel, pattern resolver
```

## Run it

```bash
cp .env.example .env       # fill in BOT_API_KEY and PG_URL
pip install pipenv && pipenv install
pipenv run python main.py
```

With Docker (brings up PostgreSQL too):

```bash
cp .env.example .env
docker compose up -d --build
```

Tests:

```bash
pipenv run pytest
```

## Configuration

| Variable | Required | What it is |
|---|---|---|
| `ENV_VALID` | yes | Must be `True`. A deliberate tripwire: set it last, once every other variable is in place |
| `BOT_API_KEY` | yes | Telegram bot token from [@BotFather](https://t.me/BotFather) |
| `PG_URL` | yes | `postgresql://user:pass@host:5432/db` |
| `ADMIN_USERNAME` | no | Telegram username allowed into `/admin` |
| `CONTENT_ITEMS_LIMIT` | no | Items shown per page in a room (default 5) |
| `TEST` | no | Test mode — uses the mock Telegram driver |

Developer notes: [docs/DEV.md](docs/DEV.md).

## License

MIT — see [LICENSE](LICENSE).

# Developer notes

The product description lives in [../README.md](../README.md); the original
Russian one is at [README.ru.md](README.ru.md).

## Environment

Copy `.env.example` to `.env` and fill it in. Every variable the code reads:

| Variable | Required | What it is |
|---|---|---|
| `ENV_VALID` | yes | Must be `True`. `config.py` exits unless it is set — a deliberate tripwire so a half-filled environment fails loudly. Set it last |
| `BOT_API_KEY` | yes | Telegram bot token from @BotFather; the bot id is derived from it |
| `PG_URL` | yes | `postgresql://user:pass@host:5432/db` |
| `ADMIN_USERNAME` | no | Telegram username allowed into `/admin` |
| `CONTENT_ITEMS_LIMIT` | no | Items shown per page inside a room (default 5) |
| `TEST` | no | Test mode: the bot talks to `bot_mock_driver` instead of Telegram |

## Running

```bash
pipenv install && pipenv run python main.py
docker compose up -d --build     # app + PostgreSQL
```

## Tests

```bash
pipenv run pytest
```

`bot_mock_driver.py` stands in for the Telegram API, so `tests/` walks whole
scenarios — creating a room, entering a key, storing content — without a
network or a bot token.

## Scenario engine

A scenario is a sequence of steps declared in `scenarios.py` on top of
`base_scenario.py`. `scenario_runner.py` keeps a user's position in the flow in
the database, so a conversation survives a restart. Adding a flow means adding
a scenario, not another branch in the handler.

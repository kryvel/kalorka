# kalorka

A small Python client and CLI for [kaloricketabulky.cz](https://www.kaloricketabulky.cz) (the
Czech nutrition tracker also known as dine4fit). It speaks the same REST endpoints that the
web UI does: log meals, water, and weight; read the daily diary, macro summary, hydration
totals, and activities synced from Apple Health.

Built around a clean `Client` class, a friendly `kalorka` CLI, and a Claude Code skill so an
LLM agent can log meals from photos or natural-language descriptions.

## Status

Alpha. Tested on macOS with Python 3.11+. The wire format is reverse-engineered from the live
site - if kaloricketabulky.cz ships a breaking change, things will break loudly. PRs welcome.

## Install

```bash
git clone https://github.com/<you>/kalorka.git
cd kalorka
python -m venv .venv && source .venv/bin/activate
pip install -e ".[rich]"
```

The `rich` extra enables pretty tables in the CLI. Drop it for a plain-text install.

## Configure credentials

Pick one. The client tries them in this order:

1. Constructor arguments: `Client(email=..., password=...)`.
2. Environment variables: `KALORKA_EMAIL`, `KALORKA_PASSWORD`.
3. **macOS Keychain** (recommended on Mac):
   ```bash
   security add-generic-password -s kalorka-email    -a "$USER" -w 'you@example.com' -U
   security add-generic-password -s kalorka-password -a "$USER" -w 'your-password'   -U
   ```
4. A config file at `$XDG_CONFIG_HOME/kalorka/credentials` (mode 0600). Two
   bare lines, no `key=` prefix - email first, password second:
   ```
   you@example.com
   your-password
   ```

Plaintext password lives nowhere except in storage you control. The client hashes it with MD5
before sending - that's what the upstream API expects, not something we chose.

## CLI

```
kalorka show               # today's diary + macro summary + hydration
kalorka show 21.05.2026
kalorka show yesterday

kalorka add --meal obed --name "Salmon bowl" --kcal 420 \
            --protein 35 --carbs 18 --fat 22

kalorka drink 500          # 500 ml of water for today
kalorka drink --date 22.05.2026 250

kalorka weight 74.2
kalorka weight --date 2026-05-21 73.8

kalorka search "omeleta"
kalorka delete <entry-id>
kalorka range 2026-05-17 2026-05-23
```

Dates accept `DD.MM.YYYY` (Czech), ISO `YYYY-MM-DD`, or the aliases `today`, `yesterday`,
`tomorrow`. Meal slots accept Czech (`snidane`, `obed`, `vecere`, `svacina`, ...) and English
(`breakfast`, `lunch`, `dinner`, ...) names.

## Library

```python
from kalorka import Client

client = Client()  # picks up credentials from env / Keychain / config

client.add_food(
    date="23.05.2026",
    meal="lunch",
    name="Salmon bowl",
    kcal=420,
    protein=35, carbs=18, fat=22,
)
client.add_drink(date="23.05.2026", milliliters=500)
client.add_weight(date="23.05.2026", kilograms=74.2)

diary = client.get_diary("23.05.2026")
print(diary.total_kcal)
for meal, items in diary.items.items():
    for item in items:
        print(meal.name, item.title, item.kcal)

summary = client.get_summary("23.05.2026")
print(summary.kcal_actual, "/", summary.kcal_goal)
```

Activities synced from Apple Health (when the kaloricketabulky iOS app is connected) appear
on `diary.activities`. There is no write endpoint for activities - the upstream service only
accepts them from its mobile app.

### Pacing

The client throttles consecutive API calls by 5-10 seconds (uniform jitter) so a batch of
writes - logging several meals + water + weight in a row - looks like a human clicking
through the UI rather than a script. The first call in a process pays no delay. Override
when you have a good reason:

```python
client = Client(min_request_interval=0.0, request_jitter=0.0)  # one-shot reads, full speed
```

See [`docs/api.md`](docs/api.md) for the full client reference and the wire format.

## Claude Code skill

`skills/kalorka/SKILL.md` is a [Claude Code skill](https://docs.claude.com/en/docs/claude-code/skills)
that teaches Claude how to log food, water, and weight from photos or text. Install it once:

```bash
ln -s "$(pwd)/skills/kalorka" ~/.claude/skills/kalorka
```

Then ask Claude things like "log my lunch: salmon bowl 420 kcal" or "I drank 500 ml of water
this morning" and it will call the CLI for you.

## Development

```bash
pip install -e ".[dev]"
pytest         # 61 tests, mocked HTTP - no network needed
ruff check .
mypy src
```

CI runs the same three commands on every push.

## License

MIT. See [LICENSE](LICENSE).

## Disclaimer

This project is not affiliated with or endorsed by kaloricketabulky.cz / dine4fit. It just
talks to their public web API the same way a browser does. Use respectfully - don't hammer
the endpoints.

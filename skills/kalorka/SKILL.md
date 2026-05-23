---
name: kalorka
description: Log meals, water, weight, and read the nutrition diary on kaloricketabulky.cz (dine4fit). Use whenever the user wants to log food/water/weight, asks about today's calories or macros, references their nutrition diary, mentions kalorka or kaloricketabulky, or shows a meal label photo to record.
---

# kalorka skill

The user has a kaloricketabulky.cz (dine4fit) account. The `kalorka` CLI lets you log food,
water, and weight, and read back the daily diary and macro summary. Use it whenever the user
asks to log something they ate/drank, asks about today's totals, or shows you a food label.

## Prerequisite

The `kalorka` command must be on PATH. Verify with `kalorka --version`. If it's missing,
tell the user how to install: `cd <kalorka repo> && pip install -e .` inside their venv.

Credentials come from the macOS Keychain (`kalorka-email`, `kalorka-password`), env vars
(`KALORKA_EMAIL`, `KALORKA_PASSWORD`), or `~/.config/kalorka/credentials`. If `kalorka show`
fails with an auth error, ask the user to set up credentials per the README.

## When to use which command

**Read the day:**
- "What did I eat today?" / "Show me my diary" / "How am I doing on calories?"
  → `kalorka show` (defaults to today)
- "...yesterday" → `kalorka show yesterday`
- "...on May 21" → `kalorka show 21.05.2026` (Czech format) or `kalorka show 2026-05-21`
- "Show me this week" → `kalorka range 2026-05-17 2026-05-23`

**Log food:**
- Photo of a meal label with macros printed on it → read the numbers off the label and call
  `kalorka add` with `--protein`, `--carbs`, `--fat`, `--fiber`, `--sugar`, `--salt` filled in.
- Free-text meal description → estimate kcal/macros, but **say out loud** what you assumed
  and from where, so the user can correct you before the entry lands.
- If the user wants a known product (like a chain restaurant item), try `kalorka search "<name>"`
  first; if it finds a match the user wants, pass that exact title to `kalorka add` for
  consistency in their history.

Example:
```bash
kalorka add --meal obed --name "Bowl s lososem" --kcal 420 \
            --protein 35 --carbs 18 --fat 22 --fiber 4
```

Meal slot accepts Czech (`snidane`, `obed`, `vecere`, `dop_svacina`, `odp_svacina`,
`druha_vecere`) or English (`breakfast`, `lunch`, `dinner`, `morning_snack`,
`afternoon_snack`, `late_snack`).

**Log water:**
- "I drank 500 ml" → `kalorka drink 500`
- "...earlier this morning" → still `kalorka drink 500` (water doesn't have meal slots; the
  upstream just tracks daily total).

**Log weight:**
- "I weigh 74.2 kg today" → `kalorka weight 74.2`
- "...this was Monday morning" → `kalorka weight --date 2026-05-18 74.2`

**Fix mistakes:**
- "Remove the last burger I logged" → run `kalorka show` first to find the entry's `id`,
  then `kalorka delete <id>`. Always confirm with the user before deleting if the id isn't
  unambiguous.

## Dates

Accept what the user gives you. The CLI understands:
- `today`, `yesterday`, `tomorrow`
- ISO: `2026-05-23`
- Czech: `23.05.2026`

If the user says something relative ("last Tuesday"), resolve it to an absolute date yourself
before passing it on; don't make the user spell it out.

## Reading photos of food labels

The user occasionally pastes photos of prepared-meal-box labels (the kind with a printed
nutrition table on the lid). Steps:

1. Read every macro number off the label literally - do not round, do not estimate. If the
   label is rotated, account for that.
2. State the values back to the user before logging so they can catch OCR mistakes.
3. Then call `kalorka add` with the exact numbers.

The label usually has: energie (kcal/kJ), bílkoviny (protein), tuky (fat), sacharidy (carbs),
cukry (sugar), vláknina (fiber), sůl (salt). Use kcal, not kJ.

## What not to do

- **Don't log without telling the user what you're about to do.** Always print the line you're
  about to add and let them ack first, unless they explicitly told you "just log it".
- **Don't invent numbers.** If macros aren't on the label or in a search result, say so and
  ask the user to fill them in, or log kcal-only.
- **Don't touch `food_log.md` or any personal nutrition journal in the working directory** -
  the CLI writes to the user's online account, not to local files. The user maintains those
  journals manually.
- **Don't try to log activities.** The upstream API doesn't accept activity writes; they only
  flow in from the iOS Apple Health bridge. You can *read* them via `kalorka show` (they
  appear in the diary entry's `activities` list).

## Confirming what landed

After any `add`/`drink`/`weight` call, run `kalorka show` for the same day so the user sees
the entry in context with the day's totals. One-line summary like "logged X, now 1240/1850
kcal for today" is usually enough.

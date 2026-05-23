"""Command-line interface for kalorka.

The CLI is intentionally thin: each subcommand maps to one method on
``Client``. It picks up ``rich`` if installed for nicer tables, and falls back
to plain text otherwise.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from typing import Any

from kalorka import __version__
from kalorka.client import Client
from kalorka.exceptions import KalorkaError
from kalorka.models import MEAL_TIME_CZECH_NAMES, DiaryEntry, MacroSummary, MealTime

try:
    from rich.console import Console
    from rich.table import Table

    _CONSOLE: Console | None = Console()
except ImportError:  # pragma: no cover - optional dependency
    _CONSOLE = None


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        rc: int = args.func(args)
    except (KalorkaError, ValueError) as exc:
        # ValueError covers client-side input validation (bad meal slot,
        # negative kg/ml, unparseable date). Surface them as clean CLI errors.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return rc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kalorka",
        description="Log nutrition data to kaloricketabulky.cz (dine4fit).",
    )
    parser.add_argument("--version", action="version", version=f"kalorka {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_show = sub.add_parser("show", help="Show diary entries and macro summary for a day")
    p_show.add_argument(
        "date",
        nargs="?",
        default="today",
        help="DD.MM.YYYY, ISO, or 'today'/'yesterday'",
    )
    p_show.set_defaults(func=_cmd_show)

    p_add = sub.add_parser("add", help="Add a custom food entry")
    p_add.add_argument("--date", default="today")
    p_add.add_argument("--meal", required=True, help="snidane|obed|vecere|... (czech or english)")
    p_add.add_argument("--name", required=True)
    p_add.add_argument("--kcal", required=True, type=float)
    p_add.add_argument("--protein", type=float)
    p_add.add_argument("--carbs", type=float)
    p_add.add_argument("--fat", type=float)
    p_add.add_argument("--fiber", type=float)
    p_add.add_argument("--sugar", type=float)
    p_add.add_argument("--salt", type=float)
    p_add.add_argument("--sat-fat", dest="sat_fat", type=float)
    p_add.set_defaults(func=_cmd_add)

    p_drink = sub.add_parser("drink", help="Log a water intake (ml)")
    p_drink.add_argument("--date", default="today")
    p_drink.add_argument("ml", type=float, help="Volume in millilitres")
    p_drink.set_defaults(func=_cmd_drink)

    p_weight = sub.add_parser("weight", help="Record a weight measurement (kg)")
    p_weight.add_argument("--date", default="today")
    p_weight.add_argument("kg", type=float)
    p_weight.set_defaults(func=_cmd_weight)

    p_delete = sub.add_parser("delete", help="Delete an entry by id (find ids via 'show')")
    p_delete.add_argument("id")
    p_delete.set_defaults(func=_cmd_delete)

    p_search = sub.add_parser("search", help="Search the food database")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=10)
    p_search.set_defaults(func=_cmd_search)

    p_range = sub.add_parser("range", help="Summarise an inclusive date range")
    p_range.add_argument("start", help="DD.MM.YYYY or ISO")
    p_range.add_argument("end", help="DD.MM.YYYY or ISO")
    p_range.set_defaults(func=_cmd_range)

    return parser


# --- subcommand implementations ---------------------------------------------


def _cmd_show(args: argparse.Namespace) -> int:
    client = Client()
    date = _resolve_date(args.date)
    diary = client.get_diary(date)
    summary = client.get_summary(date)
    drink = client.get_drink_regime(date)
    weight = client.get_weight(date)
    _render_diary(diary, summary, drink, weight)
    return 0


def _cmd_add(args: argparse.Namespace) -> int:
    Client().add_food(
        date=_resolve_date(args.date),
        meal=args.meal,
        name=args.name,
        kcal=args.kcal,
        protein=args.protein,
        carbs=args.carbs,
        fat=args.fat,
        fiber=args.fiber,
        sugar=args.sugar,
        salt=args.salt,
        saturated_fat=args.sat_fat,
    )
    print(f"added: {args.name} ({args.kcal} kcal)")
    return 0


def _cmd_drink(args: argparse.Namespace) -> int:
    Client().add_drink(date=_resolve_date(args.date), milliliters=args.ml)
    print(f"added: {args.ml:g} ml of water")
    return 0


def _cmd_weight(args: argparse.Namespace) -> int:
    Client().add_weight(date=_resolve_date(args.date), kilograms=args.kg)
    print(f"added: {args.kg:g} kg")
    return 0


def _cmd_delete(args: argparse.Namespace) -> int:
    Client().delete_entry(args.id)
    print(f"deleted: {args.id}")
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    results = Client().search_food(args.query, limit=args.limit)
    if not results:
        print("(no matches)")
        return 0
    if _CONSOLE is not None:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Title")
        table.add_column("Brand")
        table.add_column("kcal/100g", justify="right")
        table.add_column("id", style="dim")
        for r in results:
            table.add_row(
                r.title,
                r.brand or "",
                f"{r.energy_per_100g or 0:g}",
                r.id,
            )
        _CONSOLE.print(table)
    else:
        for r in results:
            brand = f" [{r.brand}]" if r.brand else ""
            print(f"  {r.title}{brand} - {r.energy_per_100g or '?'} kcal/100g (id={r.id})")
    return 0


def _cmd_range(args: argparse.Namespace) -> int:
    client = Client()
    entries = client.get_diary_range(args.start, args.end)
    rows: list[tuple[str, float, int]] = []
    for date_str, entry in entries.items():
        rows.append((date_str, entry.total_kcal, sum(len(s) for s in entry.items.values())))
    if _CONSOLE is not None:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Date")
        table.add_column("Total kcal", justify="right")
        table.add_column("Items", justify="right")
        for d, kcal, n in rows:
            table.add_row(d, f"{kcal:g}", str(n))
        _CONSOLE.print(table)
    else:
        for d, kcal, n in rows:
            print(f"  {d}  {kcal:>7g} kcal  ({n} items)")
    return 0


# --- rendering --------------------------------------------------------------


def _render_diary(
    diary: DiaryEntry,
    summary: MacroSummary,
    drink: Any,
    weight: Any,
) -> None:
    header = (
        f"{diary.date}  -  {summary.kcal_actual:g} / "
        f"{summary.kcal_goal:g} kcal ({summary.kcal_percent}%)"
    )
    if _CONSOLE is not None:
        _CONSOLE.rule(header)
    else:
        print(header)
        print("-" * len(header))

    for meal in MealTime:
        items = diary.items[meal]
        if not items:
            continue
        slot_kcal = diary.slot_kcal(meal)
        title = f"{MEAL_TIME_CZECH_NAMES[meal]} - {slot_kcal:g} kcal"
        if _CONSOLE is not None:
            table = Table(title=title, show_header=True, header_style="bold")
            table.add_column("Item")
            table.add_column("kcal", justify="right")
            table.add_column("P", justify="right")
            table.add_column("C", justify="right")
            table.add_column("F", justify="right")
            table.add_column("id", style="dim")
            for item in items:
                table.add_row(
                    item.title,
                    f"{item.kcal:g}",
                    _opt(item.protein),
                    _opt(item.carbohydrate),
                    _opt(item.fat),
                    item.id,
                )
            _CONSOLE.print(table)
        else:
            print(f"\n{title}")
            for item in items:
                bits = []
                if item.protein is not None:
                    bits.append(f"P{item.protein:g}")
                if item.carbohydrate is not None:
                    bits.append(f"C{item.carbohydrate:g}")
                if item.fat is not None:
                    bits.append(f"F{item.fat:g}")
                macros = " · " + " / ".join(bits) if bits else ""
                print(f"  - {item.title} = {item.kcal:g} kcal{macros}  id={item.id}")

    macros_line = (
        f"P {summary.protein_actual:g}/{summary.protein_goal:g}g   "
        f"C {summary.carbs_actual:g}/{summary.carbs_goal:g}g   "
        f"F {summary.fat_actual:g}/{summary.fat_goal:g}g   "
        f"Fib {summary.fiber_actual:g}/{summary.fiber_goal:g}g"
    )
    extras = []
    if drink is not None:
        extras.append(f"water {drink.liters_actual:g}/{drink.liters_goal:g} l")
    if weight is not None:
        extras.append(f"weight {weight.current_kg:g} kg (goal {weight.target_kg:g})")
    print()
    print(macros_line)
    if extras:
        print(" · ".join(extras))


def _opt(value: float | None) -> str:
    return "" if value is None else f"{value:g}"


def _resolve_date(value: str) -> str:
    """Translate friendly aliases (today/yesterday/tomorrow) into a date."""
    today = dt.date.today()
    aliases = {
        "today": today,
        "yesterday": today - dt.timedelta(days=1),
        "tomorrow": today + dt.timedelta(days=1),
    }
    if value.lower() in aliases:
        return aliases[value.lower()].strftime("%d.%m.%Y")
    return value


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

from __future__ import annotations

import datetime as dt
from unittest.mock import MagicMock, patch

import pytest

from kalorka.cli import _resolve_date, main


def test_resolve_date_today() -> None:
    expected = dt.date.today().strftime("%d.%m.%Y")
    assert _resolve_date("today") == expected


def test_resolve_date_passthrough() -> None:
    assert _resolve_date("01.01.2026") == "01.01.2026"


@pytest.mark.parametrize(
    ("argv", "method"),
    [
        (["add", "--meal", "obed", "--name", "x", "--kcal", "100"], "add_food"),
        (["drink", "500"], "add_drink"),
        (["weight", "74"], "add_weight"),
        (["delete", "abc"], "delete_entry"),
    ],
)
def test_cli_dispatches_to_client(argv: list[str], method: str) -> None:
    with patch("kalorka.cli.Client") as ClientCls:
        instance = MagicMock()
        ClientCls.return_value = instance
        rc = main(argv)
        assert rc == 0
        assert getattr(instance, method).called


def test_show_invokes_all_getters() -> None:
    from kalorka.models import MealTime

    with patch("kalorka.cli.Client") as ClientCls:
        instance = MagicMock()
        instance.get_diary.return_value = MagicMock(
            items={m: [] for m in MealTime}, date="01.01.2026"
        )
        summary = MagicMock(
            kcal_actual=0,
            kcal_goal=0,
            kcal_percent=0,
            protein_actual=0,
            protein_goal=0,
            carbs_actual=0,
            carbs_goal=0,
            fat_actual=0,
            fat_goal=0,
            fiber_actual=0,
            fiber_goal=0,
        )
        instance.get_summary.return_value = summary
        instance.get_drink_regime.return_value = None
        instance.get_weight.return_value = None
        ClientCls.return_value = instance
        assert main(["show", "01.01.2026"]) == 0
        instance.get_diary.assert_called_once()
        instance.get_summary.assert_called_once()


def test_main_reports_value_errors_cleanly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # ``kalorka drink 0`` (or any input-validation failure) should print a
    # one-line "error:" instead of leaking the traceback to the terminal.
    with patch("kalorka.cli.Client") as ClientCls:
        instance = MagicMock()
        instance.add_drink.side_effect = ValueError("milliliters must be > 0")
        ClientCls.return_value = instance
        rc = main(["drink", "0"])
    assert rc == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ")
    assert "milliliters must be > 0" in err

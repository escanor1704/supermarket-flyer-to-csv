# test_quick.py - quick tests. GitHub runs them before the pipeline, and again before the weekly file is stored
#
# How it works:   python -m pytest -v tests/test_quick.py
#   typos in the code, the settings file, the weight rules and price maths of every store,
#   and every weekly file: the 10 columns, no empty cells, real prices, the right week
#
# Tried and tuned:
#   - the tests run again right before the upload -> a broken weekly file never reaches Backblaze
#   - a test for every store's weight rule -> a change in one store can't quietly break the weight style

import csv
import glob
import os
import py_compile
import sys

import pytest
import yaml

sys.path.insert(0, "pipeline")                    # so that "import storage" finds pipeline/storage.py
import storage
import load                                       # pipeline/load.py: the weight rules of every store
import validate                                   # pipeline/validate.py: the price maths of Netto and Lidl

WEEKLY_FILES = "data/output/offers_*-W*.csv"         # one final file per week: offers_2026-W46.csv
COLUMNS = ["week", "store", "offer_start_date", "offer_end_date", "brand",
           "product_name", "product_weight", "price_eur", "offer_applied", "app_or_card_price"]


def test_code_files_have_no_typos():
    """a missing bracket or wrong indent in any .py file -> stop before running"""
    for file_name in ["run.py"] + glob.glob("pipeline/*.py"):
        py_compile.compile(file_name, doraise=True)


def test_settings_file():
    with open("config/settings.yaml", encoding="utf-8") as file:
        settings = yaml.safe_load(file)
    for key in ["stores", "data_folder", "keep_weeks"]:
        assert key in settings, "config/settings.yaml has no line for " + key
    assert isinstance(settings["stores"], list) and len(settings["stores"]) > 0, "stores: must be a list like [kaufland, netto]"


def test_week_from_flyer_name():
    assert storage.week_of("kaufland_2026-W46.pdf") == "2026-W46"
    assert storage.week_of("netto_2026-W46.pdf") == "2026-W46"
    assert storage.week_of("Prospekt KW47.pdf") is None


def test_kaufland_weight():
    """Kaufland's weight rule (load.py): the text after "je" -> '150 g', '24 x 0.33 l', 'Stück', ..."""
    assert load.kaufland_size_text("150-g-Becher") == "150 g"
    assert load.kaufland_size_text("Ka. 24 x 0,33-l-Fl.") == "24 x 0.33 l"
    assert load.kaufland_size_text("150 - 175-g-Packg.") == "150-175 g"
    assert load.kaufland_size_text("8 St. = 240-g-Packg.") == "240 g"
    assert load.kaufland_size_text("16 - 36-St.-Packg.") == "16-36 Stück"
    assert load.kaufland_size_text("Stück") == "Stück"
    assert load.kaufland_size_text("kg") == "1 kg"
    assert load.kaufland_size_text("") == "UNKNOWN"


def test_netto_weight():
    """Netto's weight rule (load.py): '0,75 Liter' -> '0.75 l', ... (the same style as Kaufland)"""
    assert load.netto_weight("0,75 Liter") == "0.75 l"
    assert load.netto_weight("300 g – 400 g") == "300-400 g"
    assert load.netto_weight("4 x 100 g") == "4 x 100 g"
    assert load.netto_weight("Stück") == "Stück"
    assert load.netto_weight("") == "UNKNOWN"


def test_netto_price_maths():
    """Netto's unit-price check (validate.py): price / size = the printed unit price"""
    assert validate.netto_money("5.-") == 5.0
    assert validate.netto_money("1.299.-") == 1299.0
    assert validate.netto_unit_price_fits(1.99, "500 g", "(3.98 / kg)")
    assert validate.netto_unit_price_fits(0.69, "0,5 Liter - 1 Liter", "(0.69 – 1.38 / l)")
    assert not validate.netto_unit_price_fits(2.99, "500 g", "(3.98 / kg)")


def test_lidl_weight():
    """Lidl's weight rule (load.py): the text after "Je" -> '100 g', '1.75 l', '2 x 100 g', 'Topf' (the same style)"""
    assert load.lidl_weight("100 g") == "100 g"
    assert load.lidl_weight("1,75 l") == "1.75 l"
    assert load.lidl_weight("2x100 g") == "2 x 100 g"
    assert load.lidl_weight("80/100 g") == "80/100 g"
    assert load.lidl_weight("Topf") == "Topf"
    assert load.lidl_weight("") == "UNKNOWN"


def test_lidl_price_maths():
    """Lidl's unit-price check (validate.py): '1 kg = 9.95' and 'Je 200 g' -> the price must be 1.99"""
    sizes = validate.lidl_all_sizes("Je 200 g; 1 kg = 9.95")
    unit_prices = validate.lidl_unit_prices_of("Je 200 g; 1 kg = 9.95")
    assert validate.lidl_fits(1.99, sizes, unit_prices)
    assert not validate.lidl_fits(2.49, sizes, unit_prices)
    assert validate.lidl_unit_prices_of("1 WL = -.19") == [(1.0, "WL", 0.19)]


def test_weekly_files_are_healthy():
    """every data/output/offers_<week>.csv: the 10 columns, no empty cells, prices are numbers,
    start date not after end date, and every row belongs to the week in the file name"""
    week_files = sorted(glob.glob(WEEKLY_FILES))
    if len(week_files) == 0:
        pytest.skip("no weekly file yet (normal before run.py and when you push code)")
    for week_file in week_files:
        name = os.path.basename(week_file)
        week = name[len("offers_"):-len(".csv")]                     # offers_2026-W46.csv -> 2026-W46
        with open(week_file, encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            assert reader.fieldnames == COLUMNS, name + " does not have the 10 expected columns"
            rows = list(reader)
        assert len(rows) > 0, name + " has no rows"
        for line, row in enumerate(rows, start=2):                   # line 1 = the column names
            where = name + " line " + str(line)
            for column in COLUMNS:
                assert row[column] not in ("", None), "empty cell in " + where + ", column " + column
            assert row["week"] == week, "a row of week " + row["week"] + " in " + where
            try:
                float(row["price_eur"])
            except ValueError:
                pytest.fail("price is not a number in " + where + ": " + row["price_eur"])
            start = row["offer_start_date"]
            end = row["offer_end_date"]
            if start[:1].isdigit() and end[:1].isdigit():            # both are real dates (not UNKNOWN)
                assert start <= end, "start date after end date in " + where
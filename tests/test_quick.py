# Quick tests - GitHub runs them before the pipeline, and once more before the offers are stored
# On your PC:  python -m pytest -v tests/test_quick.py
import csv
import glob
import os
import py_compile
import sys

import pytest
import yaml

sys.path.insert(0, "pipeline")                    # so that "import storage" finds pipeline/storage.py
import storage

OFFERS_FILE = "data/output/offers.csv"
COLUMNS = ["week", "store", "offer_start_date", "offer_end_date", "brand",
           "product_name", "product_weight", "price_eur", "offer_applied", "kaufland_card_xtra"]


def test_code_files_have_no_typos():
    """a missing bracket or wrong indent in any .py file -> stop before running"""
    for file_name in ["run.py"] + glob.glob("pipeline/*.py"):
        py_compile.compile(file_name, doraise=True)


def test_settings_file():
    with open("config/settings.yaml", encoding="utf-8") as file:
        settings = yaml.safe_load(file)
    for key in ["store", "data_folder", "keep_weeks"]:
        assert key in settings, "config/settings.yaml has no line for " + key


def test_week_from_flyer_name():
    assert storage.week_of("kaufland_2026-W46.pdf") == "2026-W46"
    assert storage.week_of("Prospekt KW47.pdf") is None


def test_offers_csv_is_healthy():
    """offers.csv: the 10 columns, no empty cells, prices are numbers, start date not after end date"""
    if not os.path.exists(OFFERS_FILE):
        pytest.skip("no offers.csv yet (normal before run.py and when you push code)")
    with open(OFFERS_FILE, encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        assert reader.fieldnames == COLUMNS, "offers.csv does not have the 10 expected columns"
        rows = list(reader)
    assert len(rows) > 0, "offers.csv has no rows"
    for line, row in enumerate(rows, start=2):           # line 1 = the column names
        for column in COLUMNS:
            assert row[column] not in ("", None), "empty cell in line " + str(line) + ", column " + column
        try:
            float(row["price_eur"])
        except ValueError:
            pytest.fail("price is not a number in line " + str(line) + ": " + row["price_eur"])
        start = row["offer_start_date"]
        end = row["offer_end_date"]
        if start[:1].isdigit() and end[:1].isdigit():    # both are real dates (not UNKNOWN)
            assert start <= end, "start date after end date in line " + str(line)
# Quick tests - GitHub runs them before the pipeline, and once more before offers.csv is saved
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
BEFORE_FILE = "data/offers_before_run.csv"        # copy made on GitHub before run.py
COLUMNS = ["week", "store", "offer_start_date", "offer_end_date", "brand",
           "product_name", "product_weight", "price_eur", "offer_applied", "kaufland_card_xtra"]


def read_rows(file_name):
    """a CSV file -> list of rows (each row = {column: value})"""
    with open(file_name, encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def rows_per_week(rows):
    """{'2026-W46 kaufland': 397, ...}"""
    counts = {}
    for row in rows:
        key = row["week"] + " " + row["store"]
        counts[key] = counts.get(key, 0) + 1
    return counts


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
        pytest.skip("no offers.csv here (normal when you push code)")
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


def test_no_old_week_lost():
    """after run.py: every OLDER week still has all its rows (only this week may change)"""
    if not os.path.exists(BEFORE_FILE) or not os.path.exists(OFFERS_FILE):
        pytest.skip("nothing to compare (this test only works on GitHub)")
    this_week = ""
    if os.path.exists("data/current_week.txt"):
        with open("data/current_week.txt", encoding="utf-8") as file:
            this_week = file.read().strip()
    before = rows_per_week(read_rows(BEFORE_FILE))
    after = rows_per_week(read_rows(OFFERS_FILE))
    for key in before:
        if this_week and key.startswith(this_week):
            continue
        assert after.get(key, 0) == before[key], key + ": " + str(before[key]) + " rows before, " + str(after.get(key, 0)) + " now"
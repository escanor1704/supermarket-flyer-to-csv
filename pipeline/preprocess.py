# preprocess.py (stage 2 of 8) - finds the new weeks and turns the flyer pages into pictures
#
# How it works:
#   python pipeline/preprocess.py plan       which weeks are new? = every flyer week that is not in data/output yet
#                                            -> data/weeks_to_do.txt (run.py goes through them, oldest first)
#   python pipeline/preprocess.py 2026-W47   the pages of week 47, for every store that still needs it -> data/pages/<store>
#   A flyer you put into data/flyers/<store> yourself (any name) gets its week from its own dates.
#   Every store writes its dates its own way: Kaufland "MONTAG, 09.11.", Netto "Montag 09.11. – Samstag 14.11.26",
#   Lidl only in the footer "47/2026".
#
# Tried and tuned:
#   - only the newest flyer was read -> Netto week 46 was never made; now every week that is not done yet is made
#   - a finished week was read again on every run -> now it is skipped

import os
import sys
import csv
import re
import shutil
import datetime
import pymupdf
import storage

WEEKS_FILE = "data/weeks_to_do.txt"


# =====================================================================================================
# KAUFLAND - writes its dates as "MONTAG, 09.11." (and once with the year: "SAMSTAG, 14.11.2026")
# =====================================================================================================
WEEKDAYS = "MONTAG|DIENSTAG|MITTWOCH|DONNERSTAG|FREITAG|SAMSTAG"


def kaufland_flyer_week(pdf):
    """read the week from the flyer's own dates -> '2026-W46'
    Kaufland writes "MONTAG, 09.11." on almost every page: the date written most often is the start day."""
    text = ""
    for page in pdf:
        text = text + page.get_text().upper() + "\n"
    # the year: from "SAMSTAG, 14.11.2026", else from any full date, else this year
    year = datetime.date.today().year
    match = re.search(r"(?:" + WEEKDAYS + r"), \d\d\.\d\d\.(\d{4})", text) or re.search(r"\d\d\.\d\d\.(\d{4})", text)
    if match:
        year = int(match.group(1))
    # every weekday date: "MONTAG, 09.11." -> 2026-11-09
    days = []
    for day, month in re.findall(r"(?:" + WEEKDAYS + r"), (\d\d)\.(\d\d)\.", text):
        try:
            days.append(datetime.date(year, int(month), int(day)))
        except ValueError:
            pass                                        # not a real date, e.g. "DONNERSTAG, 44.44."
    if len(days) == 0:
        print("WARNING: no dates found in the flyer - using this week")
        days = [datetime.date.today()]
    start = max(days, key=days.count)                   # the date written most often
    year, week_number, weekday = start.isocalendar()
    return str(year) + "-W" + str(week_number).zfill(2)


def kaufland_plan():
    """Kaufland: name your own flyers, keep the newest weeks -> the weeks of all Kaufland flyers ['2026-W46', '2026-W47']"""
    store = "kaufland"
    folder = storage.flyers_folder(store)

    # 1. a flyer without a week in its name (you put it there yourself) -> give it its week
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(".pdf") and storage.week_of(name) is None:
            pdf = pymupdf.open(folder + "/" + name)
            week = kaufland_flyer_week(pdf)
            pdf.close()                                # close it, so Windows lets us rename it
            new_name = store + "_" + week + ".pdf"
            os.replace(folder + "/" + name, folder + "/" + new_name)     # the same week again -> replaced
            print("Named your flyer:", name, "->", new_name)

    # 2. keep only the newest weeks of flyers
    storage.delete_old_flyers(store)
    flyers = storage.weekly_flyers(store)
    if len(flyers) == 0:
        print("No flyer in", folder, "- put this week's flyer there (any name) or run: python pipeline/ingest.py")
        exit(1)
    return [storage.week_of(name) for name in flyers]


def kaufland(week):
    """Kaufland: the pages of this week's flyer -> pictures + manifest.csv in data/pages/kaufland (as before)"""
    pdf_path = storage.flyer_path("kaufland", week)
    if not os.path.exists(pdf_path):
        print("No Kaufland flyer of week", week, "- Kaufland is skipped for this week")
        return
    if storage.already_done("kaufland", week):
        print("Week", week, "is already done for Kaufland ->", storage.weekly_file(week), "- not run again")
        return
    print("Working on", pdf_path)

    output_folder = "data/pages/kaufland"
    os.makedirs(output_folder, exist_ok=True)
    pdf = pymupdf.open(pdf_path)
    report = []
    for page in pdf:
        page_number = page.number + 1

        # save the page as a picture (300 DPI)
        picture = page.get_pixmap(dpi=300)
        picture_name = "page_" + str(page_number) + ".png"
        picture.save(output_folder + "/" + picture_name)

        # check if the page has real text
        text = page.get_text()
        if len(text.strip()) > 50:
            has_text = "yes"
        else:
            has_text = "no"
        print("Page", page_number, "- text layer:", has_text)
        report.append([page_number, has_text, picture_name])
    pdf.close()

    # save the report as a CSV file
    with open(output_folder + "/manifest.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["page", "has_text_layer", "picture"])
        writer.writerows(report)

    print("Done! Week", week, "- pictures and manifest.csv saved in", output_folder)


# =====================================================================================================
# NETTO - writes its dates as "Montag 09.11. – Samstag 14.11.26" (or one day: "Dienstag, 10.11.2026")
# =====================================================================================================
NETTO_WEEKDAYS = "Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag"


def netto_flyer_week(pdf):
    """read the week from the flyer's own dates -> '2026-W46'
    Netto writes "Montag 09.11. – Samstag 14.11.26" on almost every page: the date written most often is the start day."""
    text = ""
    for page in pdf:
        text = text + page.get_text() + "\n"
    text = text.replace("\u2009", " ").replace("\u202f", " ").replace("\xa0", " ")      # thin spaces -> normal spaces
    # the year: "Samstag 14.11.26" or "Dienstag, 10.11.2026", else this year
    year = datetime.date.today().year
    match = re.search(r"(?:" + NETTO_WEEKDAYS + r"),? \d\d\.\d\d\.(\d{4}|\d\d)\b", text, re.IGNORECASE)
    if match:
        year = int(match.group(1))
        if year < 100:
            year = 2000 + year                          # "26" -> 2026
    # every weekday date: "Montag 09.11." -> 2026-11-09
    days = []
    for day, month in re.findall(r"(?:" + NETTO_WEEKDAYS + r"),? (\d\d)\.(\d\d)\.", text, re.IGNORECASE):
        try:
            days.append(datetime.date(year, int(month), int(day)))
        except ValueError:
            pass                                        # not a real date
    if len(days) == 0:
        print("WARNING: no dates found in the Netto flyer - using this week")
        days = [datetime.date.today()]
    start = max(days, key=days.count)                   # the date written most often (every day of it is in the same week)
    year, week_number, weekday = start.isocalendar()
    return str(year) + "-W" + str(week_number).zfill(2)


def netto_plan():
    """Netto: name your own flyers, keep the newest weeks -> the weeks of all Netto flyers ['2026-W46', '2026-W47']"""
    store = "netto"
    folder = storage.flyers_folder(store)

    # 1. a flyer without a week in its name (you put it there yourself) -> give it its week
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(".pdf") and storage.week_of(name) is None:
            pdf = pymupdf.open(folder + "/" + name)
            week = netto_flyer_week(pdf)
            pdf.close()                                # close it, so Windows lets us rename it
            new_name = store + "_" + week + ".pdf"
            os.replace(folder + "/" + name, folder + "/" + new_name)     # the same week again -> replaced
            print("Named your flyer:", name, "->", new_name)

    # 2. keep only the newest weeks of flyers
    storage.delete_old_flyers(store)
    flyers = storage.weekly_flyers(store)
    if len(flyers) == 0:
        print("No Netto flyer in", folder, "- Netto is skipped (Kaufland goes on)")
    return [storage.week_of(name) for name in flyers]


def netto(week):
    """Netto: the pages of this week's flyer -> pictures + manifest.csv in data/pages/netto"""
    pdf_path = storage.flyer_path("netto", week)
    if not os.path.exists(pdf_path):
        print("No Netto flyer of week", week, "- Netto is skipped for this week")
        return
    if storage.already_done("netto", week):
        print("Week", week, "is already done for Netto ->", storage.weekly_file(week), "- not run again")
        return
    print("Working on", pdf_path)

    output_folder = "data/pages/netto"
    os.makedirs(output_folder, exist_ok=True)
    pdf = pymupdf.open(pdf_path)
    report = []
    for page in pdf:
        page_number = page.number + 1
        picture = page.get_pixmap(dpi=300)                 # the page as a picture (300 DPI)
        picture_name = "page_" + str(page_number) + ".png"
        picture.save(output_folder + "/" + picture_name)
        has_text = "yes" if len(page.get_text().strip()) > 50 else "no"
        print("Page", page_number, "- text layer:", has_text)
        report.append([page_number, has_text, picture_name])
    pdf.close()
    with open(output_folder + "/manifest.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["page", "has_text_layer", "picture"])
        writer.writerows(report)

    print("Done! Week", week, "- pictures and manifest.csv saved in", output_folder)


# =====================================================================================================
# LIDL - prints its edition in the footer: "HHZ – 47/2026 – DE" (week 47 of 2026)
# =====================================================================================================
def lidl_flyer_week(pdf):
    """read the week from the footer of the flyer -> '2026-W47'   (the edition printed most often)"""
    editions = []
    for page in pdf:
        for week_text, year_text in re.findall(r"\b(\d{1,2})/(20\d\d)\b", page.get_text()):
            if 1 <= int(week_text) <= 53:
                editions.append((int(year_text), int(week_text)))
    if editions:
        year, week_number = max(set(editions), key=editions.count)
    else:
        print("WARNING: no edition like '47/2026' found in the Lidl flyer - using this week")
        year, week_number, weekday = datetime.date.today().isocalendar()
    return str(year) + "-W" + str(week_number).zfill(2)


def lidl_plan():
    """Lidl: name your own flyers, keep the newest weeks -> the weeks of all Lidl flyers ['2026-W46', '2026-W47']"""
    store = "lidl"
    folder = storage.flyers_folder(store)

    # 1. a flyer without a week in its name (you put it there yourself) -> give it its week
    for name in sorted(os.listdir(folder)):
        if name.lower().endswith(".pdf") and storage.week_of(name) is None:
            pdf = pymupdf.open(folder + "/" + name)
            week = lidl_flyer_week(pdf)
            pdf.close()                                # close it, so Windows lets us rename it
            new_name = store + "_" + week + ".pdf"
            os.replace(folder + "/" + name, folder + "/" + new_name)     # the same week again -> replaced
            print("Named your flyer:", name, "->", new_name)

    # 2. keep only the newest weeks of flyers
    storage.delete_old_flyers(store)
    flyers = storage.weekly_flyers(store)
    if len(flyers) == 0:
        print("No Lidl flyer in", folder, "- Lidl is skipped (Kaufland goes on)")
    return [storage.week_of(name) for name in flyers]


def lidl(week):
    """Lidl: the pages of this week's flyer -> pictures + manifest.csv in data/pages/lidl"""
    pdf_path = storage.flyer_path("lidl", week)
    if not os.path.exists(pdf_path):
        print("No Lidl flyer of week", week, "- Lidl is skipped for this week")
        return
    if storage.already_done("lidl", week):
        print("Week", week, "is already done for Lidl ->", storage.weekly_file(week), "- not run again")
        return
    print("Working on", pdf_path)

    output_folder = "data/pages/lidl"
    os.makedirs(output_folder, exist_ok=True)
    pdf = pymupdf.open(pdf_path)
    report = []
    for page in pdf:
        page_number = page.number + 1
        picture = page.get_pixmap(dpi=300)                 # the page as a picture (300 DPI)
        picture_name = "page_" + str(page_number) + ".png"
        picture.save(output_folder + "/" + picture_name)
        has_text = "yes" if len(page.get_text().strip()) > 50 else "no"
        print("Page", page_number, "- text layer:", has_text)
        report.append([page_number, has_text, picture_name])
    pdf.close()
    with open(output_folder + "/manifest.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["page", "has_text_layer", "picture"])
        writer.writerows(report)

    print("Done! Week", week, "- pictures and manifest.csv saved in", output_folder)


# =====================================================================================================
# RUN (only when started as a program - not when the tests read this file)
# =====================================================================================================
STORE_PLANS = {"kaufland": kaufland_plan, "netto": netto_plan, "lidl": lidl_plan}
STORE_PARTS = {"kaufland": kaufland, "netto": netto, "lidl": lidl}


def plan():
    """every store: name + clean up its flyers -> the weeks that are not in data/output yet (oldest first)"""
    weeks_to_do = []
    for store in storage.stores():
        if store not in STORE_PLANS:
            print("\n" + store + ": preprocess.py has no function for this store yet - skipped")
            continue
        print("\n----- " + store + " -----")
        try:
            for week in STORE_PLANS[store]():
                if storage.already_done(store, week):
                    print("Week", week, "is already done ->", storage.weekly_file(week))
                else:
                    print("Week", week, "is NEW -> will be made")
                    if week not in weeks_to_do:
                        weeks_to_do.append(week)
        except Exception as error:
            storage.store_failed(store, "preprocess (plan)", error)
    weeks_to_do.sort()
    with open(WEEKS_FILE, "w", encoding="utf-8") as file:
        file.write("\n".join(weeks_to_do))
    if weeks_to_do:
        print("\nWeeks to do:", ", ".join(weeks_to_do), "(saved in " + WEEKS_FILE + ")")
    else:
        print("\nNothing new: every flyer week is already in data/output (to make a week again: delete its offers_<week>.csv)")
    return weeks_to_do


def pictures(week):
    """one week: start clean, remember the week, then the pictures of every store that still needs this week"""
    # start clean: the work files and results of the last week are removed (they are made again)
    try:
        for store in storage.stores():
            for folder in ["data/pages/", "data/text/", "data/offers/"]:
                if os.path.exists(folder + store):
                    shutil.rmtree(folder + store)
            for file_name in ["offers_checked.csv", "offers_verified.csv", "not_offers.csv"]:
                if os.path.exists("data/review/" + store + "/" + file_name):
                    os.remove("data/review/" + store + "/" + file_name)
    except PermissionError as error:
        print("Could not delete", error.filename, "- is it open (e.g. in Excel)? Close it and run again.")
        exit(1)
    storage.save_current_week(week)                    # the next stages work on this week
    print("Week", week)
    for store in storage.stores():
        if store not in STORE_PARTS:
            continue
        print("\n----- " + store + " -----")
        try:
            STORE_PARTS[store](week)
        except Exception as error:
            storage.store_failed(store, "preprocess", error)


if __name__ == "__main__":
    argument = sys.argv[1] if len(sys.argv) > 1 else ""
    if argument == "plan":
        plan()
    elif re.fullmatch(r"\d{4}-W\d\d", argument):
        pictures(argument)
    elif argument == "":
        weeks = plan()
        if weeks:
            pictures(weeks[0])
    else:
        print("Unknown argument:", argument, "- use: plan, a week like 2026-W47, or nothing")
        exit(1)
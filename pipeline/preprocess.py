# Stage 1: pick this week's flyer from data/flyers/kaufland and turn its pages into pictures
#   All flyers of a store live in ONE folder: data/flyers/kaufland/kaufland_2026-W46.pdf
#   (ingest.py downloads them there; you can also put a flyer there yourself, with any name)
#   1. a flyer you put there yourself gets its week from its own dates: Prospekt.pdf -> kaufland_2026-W46.pdf
#   2. the pipeline works on the NEWEST week and remembers it (data/current_week.txt)
#   3. only the newest 4 weeks of flyers are kept (keep_weeks in config/settings.yaml)
#   4. every page is saved as a picture + checked for real text (as before)

import os
import csv
import re
import datetime
import pymupdf
import storage

WEEKDAYS = "MONTAG|DIENSTAG|MITTWOCH|DONNERSTAG|FREITAG|SAMSTAG"


def flyer_week(pdf):
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


store = storage.settings()["store"]
folder = storage.flyers_folder()
storage.move_old_flyers()                              # one time: flyers from the old folders inbox/ and raw/

# 1. a flyer without a week in its name (you put it there yourself) -> give it its week
for name in sorted(os.listdir(folder)):
    if name.lower().endswith(".pdf") and storage.week_of(name) is None:
        pdf = pymupdf.open(folder + "/" + name)
        week = flyer_week(pdf)
        pdf.close()                                    # close it, so Windows lets us rename it
        new_name = store + "_" + week + ".pdf"
        os.replace(folder + "/" + name, folder + "/" + new_name)     # the same week again -> replaced
        print("Named your flyer:", name, "->", new_name)

# 2. the newest week is the one we work on
flyers = storage.weekly_flyers()
if len(flyers) == 0:
    print("No flyer in", folder, "- put this week's flyer there (any name) or run: python pipeline/ingest.py")
    exit(1)
week = storage.week_of(flyers[-1])
storage.save_current_week(week)
pdf_path = storage.flyer_path(week)
print("Working on week", week, "->", pdf_path)

# 3. keep only the newest weeks of flyers
storage.delete_old_flyers()

# 4. turn each page into a picture and check if it has real text (as before)
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
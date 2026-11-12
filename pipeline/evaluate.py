# Stage 7: quality report - how well did this week's run go?  (version 3)
# Runs inside run.py right after load.py (before the clean-up deletes the work files).
# Shows the FINAL numbers (after the repairs of verify.py) and saves them in logs/quality_report.txt,
# so after an automatic weekly run you can see at one glance if everything went well.
# (The page details - empty pages, prices without a product - are left out for now: coupon pages and
#  pages with products made them confusing. We can add a better version later.)

import os
import csv
import datetime
import storage

review_folder = "data/review/kaufland"
summary_file = "data/offers/kaufland/page_summary.csv"
report_file = "logs/quality_report.txt"


def read_rows(file_name):
    """all rows of a CSV file (an empty list if the file is not there)"""
    if not os.path.exists(file_name):
        return []
    with open(file_name, encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


# 1. read what this run produced
found = read_rows(review_folder + "/offers_checked.csv")          # every product found on the flyer
final = read_rows(review_folder + "/offers_verified.csv")          # -> went into data/output/offers.csv
review = read_rows(review_folder + "/needs_review.csv")            # -> set aside, you look at these
removed = read_rows(review_folder + "/not_offers.csv")             # -> banners, letters, ads (not products)
pages = read_rows(summary_file)                                    # what was found on each page

if len(found) == 0:
    print("No results of this run found - run the pipeline first: python run.py")
    exit()

# 2. the numbers
week = found[0]["week"]
store = found[0]["store"]
products = len(found) - len(removed)                               # real products (without banners/ads)
share = round(100 * len(final) / products) if products > 0 else 0
page_errors = [p["page"] + ": " + p["error"] for p in pages if p.get("error")]

# was this week's flyer used? the week of TOMORROW is expected (a run on Sunday expects Monday's new flyer)
year, week_number, weekday = (datetime.date.today() + datetime.timedelta(days=1)).isocalendar()
expected_week = str(year) + "-W" + str(week_number).zfill(2)
flyer_week = storage.current_week()                                # the flyer this run worked on

# 3. the verdict: OK, or what to check
warnings = []
if len(final) == 0:
    warnings.append("NO offers reached the final file - did Kaufland change the flyer design?")
elif share < 70:
    warnings.append("only " + str(share) + "% of the products reached the final file - look at needs_review.csv")
if page_errors:
    warnings.append(str(len(page_errors)) + " page(s) could not be read")
if flyer_week < expected_week:
    warnings.append("the flyer of " + expected_week + " was not downloaded - this run used the older flyer of " + flyer_week)

# 4. write the report
lines = []
lines.append("QUALITY REPORT - " + store + " " + week + " - " + str(len(pages)) + " pages")
lines.append("")
lines.append("Products found on the flyer:   " + str(products))
lines.append("In the final file:             " + str(len(final)) + "  (" + str(share) + "%)  -> data/output/offers.csv")
lines.append("Set aside, please check:       " + str(len(review)) + "  -> " + review_folder + "/needs_review.csv")
for error in page_errors:
    lines.append("Page error:                    page " + error)
lines.append("")
if warnings:
    for warning in warnings:
        lines.append("CHECK: " + warning)
else:
    lines.append("Verdict: OK")

os.makedirs("logs", exist_ok=True)
with open(report_file, "w", encoding="utf-8") as file:
    file.write("\n".join(lines) + "\n")
print("\n".join(lines))
print("\n(saved in " + report_file + ")")
# evaluate.py (stage 8 of 8) - the quality report: how well did this week go?
#
# How it works:
#   For every store: how many products were found, how many reached the weekly file, how many are set aside.
#   CHECK lines when something looks wrong: less than 70% made it, a page could not be read, a flyer was not downloaded.
#   -> logs/quality_report.txt (one part per week made in this run; GitHub shows it on the run page)
#
# Tried and tuned:
#   - it listed every empty page and every leftover price -> too confusing (coupon pages), now only the numbers that matter

import os
import csv
import datetime
import storage

report_file = "logs/quality_report.txt"


def read_rows(file_name):
    """all rows of a CSV file (an empty list if the file is not there)"""
    if not os.path.exists(file_name):
        return []
    with open(file_name, encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def expected_week():
    """the week of TOMORROW: a run on Sunday expects Monday's new flyer -> '2026-W47'"""
    year, week_number, weekday = (datetime.date.today() + datetime.timedelta(days=1)).isocalendar()
    return str(year) + "-W" + str(week_number).zfill(2)


# =====================================================================================================
# KAUFLAND
# =====================================================================================================
def kaufland(week):
    """Kaufland's part of the report of one week -> (lines, warnings)"""
    review_folder = "data/review/kaufland"
    found = read_rows(review_folder + "/offers_checked.csv")          # every product found on the flyer
    final = read_rows(review_folder + "/offers_verified.csv")          # -> went into data/output/offers_<week>.csv
    review = read_rows(review_folder + "/needs_review.csv")            # -> set aside, you look at these
    removed = read_rows(review_folder + "/not_offers.csv")             # -> banners, letters, ads (not products)
    pages = read_rows("data/offers/kaufland/page_summary.csv")         # what was found on each page
    newest_week = storage.week_of(os.path.basename(storage.newest_flyer("kaufland") or ""))

    # the newest Kaufland flyer is older than this week's? -> the download did not work
    warnings = []
    if week == newest_week and week < expected_week():
        warnings.append("the Kaufland flyer of " + expected_week() + " was not downloaded - the newest one is " + week)

    if not os.path.exists(storage.flyer_path("kaufland", week)):
        return ["KAUFLAND " + week + ": no flyer of this week", ""], warnings
    if len(found) == 0 and storage.already_done("kaufland", week):
        return ["KAUFLAND " + week + ": already done in an earlier run -> " + storage.weekly_file(week), ""], warnings
    if len(found) == 0:
        return (["KAUFLAND " + week + ": no results - look for its error in the log above", ""],
                warnings + ["Kaufland has no offers in " + week])

    # the numbers
    products = len(found) - len(removed)                               # real products (without banners/ads)
    share = round(100 * len(final) / products) if products > 0 else 0
    page_errors = [p["page"] + ": " + p["error"] for p in pages if p.get("error")]

    # what to check
    if len(final) == 0:
        warnings.append("NO Kaufland offers reached the final file - did Kaufland change the flyer design?")
    elif share < 70:
        warnings.append("only " + str(share) + "% of the Kaufland products reached the final file - look at "
                        + review_folder + "/needs_review.csv")
    if page_errors:
        warnings.append("Kaufland: " + str(len(page_errors)) + " page(s) could not be read")

    lines = []
    lines.append("KAUFLAND " + week + " - " + str(len(pages)) + " pages")
    lines.append("Products found on the flyer:   " + str(products))
    lines.append("In the final file:             " + str(len(final)) + "  (" + str(share) + "%)  -> " + storage.weekly_file(week))
    lines.append("Set aside, please check:       " + str(len(review)) + "  -> " + review_folder + "/needs_review.csv")
    for error in page_errors:
        lines.append("Page error:                    page " + error)
    lines.append("")
    return lines, warnings


# =====================================================================================================
# NETTO
# =====================================================================================================
def netto(week):
    """Netto's part of the report of one week -> (lines, warnings)"""
    review_folder = "data/review/netto"
    found = read_rows(review_folder + "/offers_checked.csv")          # every product (+ every price without a product)
    final = read_rows(review_folder + "/offers_verified.csv")          # -> went into data/output/offers_<week>.csv
    review = read_rows(review_folder + "/needs_review.csv")            # -> set aside, you look at these
    removed = read_rows(review_folder + "/not_offers.csv")             # -> banners, prices without a product, repeats
    pages = read_rows("data/offers/netto/page_summary.csv")            # what was found on each page
    newest_week = storage.week_of(os.path.basename(storage.newest_flyer("netto") or ""))

    # the newest Netto flyer is older than this week's? -> the download did not work
    warnings = []
    if newest_week is None:
        warnings.append("no Netto flyer at all - was it downloaded? (see the ingest SUMMARY)")
    elif week == newest_week and week < expected_week():
        warnings.append("the Netto flyer of " + expected_week() + " was not downloaded - the newest one is " + week)

    if not os.path.exists(storage.flyer_path("netto", week)):
        return ["NETTO " + week + ": no flyer of this week", ""], warnings
    if len(found) == 0 and storage.already_done("netto", week):
        return ["NETTO " + week + ": already done in an earlier run -> " + storage.weekly_file(week), ""], warnings
    if len(found) == 0:
        return (["NETTO " + week + ": FAILED - look for its WARNING in the log above", ""],
                warnings + ["Netto failed in " + week + " - its offers are NOT in the final file"])

    # the numbers
    products = len(found) - len(removed)                               # real products (without banners/repeats)
    share = round(100 * len(final) / products) if products > 0 else 0
    page_errors = [p["page"] + ": " + p["error"] for p in pages if p.get("error")]

    # what to check
    if len(final) == 0:
        warnings.append("NO Netto offers reached the final file - did Netto change the flyer design (fonts)?")
    elif share < 70:
        warnings.append("only " + str(share) + "% of the Netto products reached the final file - look at "
                        + review_folder + "/needs_review.csv")
    if page_errors:
        warnings.append("Netto: " + str(len(page_errors)) + " page(s) could not be read")

    lines = []
    lines.append("NETTO " + week + " - " + str(len(pages)) + " pages")
    lines.append("Products found on the flyer:   " + str(products))
    lines.append("In the final file:             " + str(len(final)) + "  (" + str(share) + "%)  -> " + storage.weekly_file(week))
    lines.append("Set aside, please check:       " + str(len(review)) + "  -> " + review_folder + "/needs_review.csv")
    for error in page_errors:
        lines.append("Page error:                    page " + error)
    lines.append("")
    return lines, warnings


# =====================================================================================================
# LIDL
# =====================================================================================================
def lidl(week):
    """Lidl's part of the report of one week -> (lines, warnings)"""
    review_folder = "data/review/lidl"
    found = read_rows(review_folder + "/offers_checked.csv")          # every product (+ every price without a product)
    final = read_rows(review_folder + "/offers_verified.csv")          # -> went into data/output/offers_<week>.csv
    review = read_rows(review_folder + "/needs_review.csv")            # -> set aside, you look at these
    removed = read_rows(review_folder + "/not_offers.csv")             # -> headlines, prices without a product, repeats
    pages = read_rows("data/offers/lidl/page_summary.csv")             # what was found on each page
    newest_week = storage.week_of(os.path.basename(storage.newest_flyer("lidl") or ""))

    # the newest Lidl flyer is older than this week's? -> the download did not work
    warnings = []
    if newest_week is None:
        warnings.append("no Lidl flyer at all - was it downloaded? (see the ingest SUMMARY)")
    elif week == newest_week and week < expected_week():
        warnings.append("the Lidl flyer of " + expected_week() + " was not downloaded - the newest one is " + week)

    if not os.path.exists(storage.flyer_path("lidl", week)):
        return ["LIDL " + week + ": no flyer of this week", ""], warnings
    if len(found) == 0 and storage.already_done("lidl", week):
        return ["LIDL " + week + ": already done in an earlier run -> " + storage.weekly_file(week), ""], warnings
    if len(found) == 0:
        return (["LIDL " + week + ": FAILED - look for its WARNING in the log above", ""],
                warnings + ["Lidl failed in " + week + " - its offers are NOT in the final file"])

    # the numbers
    products = len(found) - len(removed)                               # real products (without headlines/repeats)
    share = round(100 * len(final) / products) if products > 0 else 0
    page_errors = [p["page"] + ": " + p["error"] for p in pages if p.get("error")]
    no_price_pages = [p["page"] for p in pages if p.get("prices") == "0" and p.get("products") not in ("0", "", None)]

    # what to check
    if len(final) == 0:
        warnings.append("NO Lidl offers reached the final file - did Lidl change the flyer design?")
    elif share < 70:
        warnings.append("only " + str(share) + "% of the Lidl products reached the final file - look at "
                        + review_folder + "/needs_review.csv")
    if page_errors:
        warnings.append("Lidl: " + str(len(page_errors)) + " page(s) could not be read")

    lines = []
    lines.append("LIDL " + week + " - " + str(len(pages)) + " pages")
    lines.append("Products found on the flyer:   " + str(products))
    lines.append("In the final file:             " + str(len(final)) + "  (" + str(share) + "%)  -> " + storage.weekly_file(week))
    lines.append("Set aside, please check:       " + str(len(review)) + "  -> " + review_folder + "/needs_review.csv")
    if no_price_pages:
        lines.append("Pages with no price as text:   " + ", ".join(no_price_pages) + "  (the prices there are pictures)")
    for error in page_errors:
        lines.append("Page error:                    page " + error)
    lines.append("")
    return lines, warnings


# =====================================================================================================
# RUN: the report of the week the pipeline is working on (data/current_week.txt), every store, then the verdict
# (only when started as a program - python pipeline/evaluate.py - not when the tests read this file)
# =====================================================================================================
if __name__ == "__main__":
    STORE_PARTS = {"kaufland": kaufland, "netto": netto, "lidl": lidl}

    # was there any result at all? (after the clean-up the work files are gone)
    if not any(os.path.exists("data/review/" + store + "/offers_checked.csv") for store in storage.stores()):
        print("No results of this week found - run the pipeline: python run.py")
        exit()

    week = storage.current_week()
    lines = ["QUALITY REPORT - week " + week, ""]
    warnings = []
    for store in storage.stores():
        if store in STORE_PARTS:
            store_lines, store_warnings = STORE_PARTS[store](week)
            lines = lines + store_lines
            warnings = warnings + store_warnings

    # the verdict: OK, or what to check
    if warnings:
        for warning in warnings:
            lines.append("CHECK: " + warning)
    else:
        lines.append("Verdict: OK")

    # ADD this week's report to the report file (run.py starts a new file at the start of every run,
    # so a run that makes week 46 and week 47 shows both reports)
    os.makedirs("logs", exist_ok=True)
    with open(report_file, "a", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n\n")
    print("\n".join(lines))
    print("\n(added to " + report_file + ")")
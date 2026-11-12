# Stage 7: add this flyer's offers to the final files
#   data/output/offers.csv           -> the SIMPLE final file (10 columns)
#   data/output/offers_detailed.csv  -> more columns (for checking and later steps)
# Only the OFFER price goes into these files. The old (crossed-out) price and the XTRA price are often
# missing on the flyer, so they would make empty columns. They are still used inside the checks.
# No cell is ever empty: missing values get a default ("no", "0", "none" or "UNKNOWN").

import os
import csv
import re
import shutil

new_file = "data/review/kaufland/offers_verified.csv"     # only the good offers (after deep verification)
simple_file = "data/output/offers.csv"
detailed_file = "data/output/offers_detailed.csv"
os.makedirs("data/output", exist_ok=True)

SIMPLE_COLUMNS = ["week", "store", "offer_start_date", "offer_end_date", "brand",
                  "product_name", "product_weight", "price_eur", "offer_applied", "kaufland_card_xtra"]
NOT_IN_DATA_FILES = ["regular_price_eur", "xtra_price_eur", "xtra"]     # often empty -> left out of both files


def number_text(value):
    """'500.0' -> '500' ,  '0.7' -> '0.7' ,  '0,33' -> '0.33'"""
    number = float(str(value).replace(",", "."))
    if number == int(number):
        return str(int(number))
    return str(round(number, 3))


def product_weight(row):
    """The weight as the flyer shows it: '500 g', '150-175 g', '24 x 0.33 l', '1 piece'"""
    # a crate or multipack that verify.py repaired: "multipack 24 x 0.33 l"
    match = re.search(r"multipack (\d+) x ([\d.]+) (\w+)", row.get("verify_note", ""))
    if match:
        return match.group(1) + " x " + number_text(match.group(2)) + " " + match.group(3)
    # another size that verify.py found: "28-g-Rollen bzw. 90-g-Packg." -> "90 g"
    if "fits the unit price" in row.get("verify_note", ""):
        return number_text(row["pack_size"]) + " " + row["unit"]
    # a range: "150 - 175-g-Packg." -> "150-175 g"
    match = re.search(r"([\d,]+) - ([\d,]+)[- ]?(kg|g|ml|l)\b", row["weight"])
    if match:
        return number_text(match.group(1)) + "-" + number_text(match.group(2)) + " " + match.group(3)
    # a normal size: "500.0" + "g" -> "500 g"   ("135" + "piece" -> "135 pieces")
    if row["pack_size"]:
        unit = row["unit"]
        if unit == "piece" and number_text(row["pack_size"]) != "1":
            unit = "pieces"
        return number_text(row["pack_size"]) + " " + unit
    return ""


def price_text(value):
    """'9.0' -> '9.00' ,  '1.49' -> '1.49'  (always 2 decimals, like on the flyer)"""
    if value == "":
        return ""
    return f"{float(value):.2f}"


# no empty cells in the data files: an empty cell gets a default value
#   yes/no columns -> "no",  "nothing" numbers -> "0",  no label / no problem -> "none",  everything else -> "UNKNOWN"
DEFAULTS = {"kaufland_card_xtra": "no", "offer_applied": "no", "discount_pct": "0", "deposit_eur": "0",
            "label": "none", "problems": "none", "verify_note": "none"}


def fill_empty(row, columns):
    """put a default value into every empty cell of this row"""
    for column in columns:
        if str(row.get(column, "") or "").strip() == "":
            row[column] = DEFAULTS.get(column, "UNKNOWN")


def is_date(text):
    """True for '2026-11-14' (False for '' or 'UNKNOWN')"""
    return re.fullmatch(r"\d{4}-\d\d-\d\d", text or "") is not None


def start_and_end(row):
    """the offer dates of a row (the simple file says offer_start_date, the detailed file valid_from)"""
    start = row.get("offer_start_date") or row.get("valid_from") or ""
    end = row.get("offer_end_date") or row.get("valid_to") or ""
    return start, end


def save_with_replace(final_file, rows, columns):
    """Add rows to a final file. Old rows of the SAME FLYER are replaced, so a rerun never doubles.
    Same flyer = same week + store, OR same store + same last offer day (also catches a flyer saved under a wrong week).
    Old rows with broken dates (start after end, e.g. 2026-12-19 -> 2026-11-14) are removed.
    If the file was made by an OLDER version of the code (other columns), it is put aside and a new file starts."""
    new_keys = []              # (week, store) of this flyer
    new_ends = []              # (store, last offer day) of this flyer
    for row in rows:
        if (row["week"], row["store"]) not in new_keys:
            new_keys.append((row["week"], row["store"]))
        start, end = start_and_end(row)
        if is_date(end) and (row["store"], end) not in new_ends:
            new_ends.append((row["store"], end))
    old_rows_kept = []
    replaced = 0
    if os.path.exists(final_file):
        with open(final_file, encoding="utf-8-sig") as file:
            old_columns = csv.DictReader(file).fieldnames
        if old_columns != columns:
            old_version = final_file.replace(".csv", "_old_version.csv")
            os.replace(final_file, old_version)                                    # put the old file aside
            print("Note:", final_file, "had other columns (older code) -> moved to", old_version, "- starting a new file")
    if os.path.exists(final_file):
        shutil.copy(final_file, final_file.replace(".csv", "_backup.csv"))     # safety copy
        with open(final_file, encoding="utf-8-sig") as file:
            for row in csv.DictReader(file):
                start, end = start_and_end(row)
                same_flyer = (row.get("week"), row.get("store")) in new_keys or (row.get("store"), end) in new_ends
                broken_dates = is_date(start) and is_date(end) and start > end
                if same_flyer or broken_dates:
                    replaced = replaced + 1          # replaced by the new rows (or removed: broken dates)
                else:
                    old_rows_kept.append(row)        # another flyer (another week) -> keep it
    all_rows = old_rows_kept + rows
    for row in all_rows:
        fill_empty(row, columns)
    with open(final_file, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerows(all_rows)
    return new_keys, len(old_rows_kept), replaced, len(all_rows)


# 1. read this flyer's good offers
with open(new_file, encoding="utf-8-sig") as file:
    new_rows = list(csv.DictReader(file))
if len(new_rows) == 0:
    print("No offers in", new_file, "- nothing to add.")
    exit()
detailed_columns = []
for column in new_rows[0].keys():
    if column not in NOT_IN_DATA_FILES:
        detailed_columns.append(column)
detailed_columns.append("kaufland_card_xtra")

# 2. make the simple rows
simple_rows = []
for r in new_rows:
    if r["regular_price_eur"] or r["discount_pct"] or r["label"] or r["xtra_price_eur"]:
        offer_applied = "yes"        # old price, -XX%, a label like KNÜLLER / AKTION, or an XTRA price
    else:
        offer_applied = "no"
    if r.get("xtra", "") == "yes":
        r["kaufland_card_xtra"] = "yes"     # the flyer shows an extra price for Kaufland Card XTRA members
    else:
        r["kaufland_card_xtra"] = "no"      # not mentioned -> "no" (never empty)
    if r["brand"].strip() == "":
        r["brand"] = "UNKNOWN"              # no brand in capitals on the flyer
    simple_rows.append({
        "week": r["week"],
        "store": r["store"],
        "offer_start_date": r["valid_from"],
        "offer_end_date": r["valid_to"],
        "brand": r["brand"],
        "product_name": r["product_name"],  # without the brand
        "product_weight": product_weight(r),
        "price_eur": price_text(r["offer_price_eur"]),
        "offer_applied": offer_applied,
        "kaufland_card_xtra": r["kaufland_card_xtra"],
    })

# 3. save both final files
keys, kept, replaced, total = save_with_replace(simple_file, simple_rows, SIMPLE_COLUMNS)
save_with_replace(detailed_file, new_rows, detailed_columns)

print("Flyer:", keys)
print("Old rows kept:", kept, "| old rows replaced:", replaced, "| new rows added:", len(simple_rows))
print("Done! The final file now has", total, "offers:", simple_file, "(all details in " + detailed_file + ")")
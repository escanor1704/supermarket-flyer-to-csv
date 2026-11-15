# Stage 7: add this week's offers of every store to the final files  -  version 3: one file per week
#   data/output/offers_2026-W46.csv           -> the SIMPLE final file of ONE week (10 columns), all stores together
#   data/output/offers_2026-W47.csv              (column "store" says kaufland / netto). Older weeks are never touched.
#   data/output/offers_detailed_<store>.csv   -> more columns, one file per store (for checking and later steps)
# kaufland() and netto() each turn ONE of their verified rows into a row of the final file, with their own
# weight rule (both write the weight in the same style: '500 g', '0.75 l', '24 x 0.33 l', 'Stück').
# Only the OFFER price goes into these files. The old (crossed-out) price and the XTRA price are often
# missing on the flyer, so they would make empty columns. They are still used inside the checks.
# No cell is ever empty: missing values get a default ("no", "0", "none" or "UNKNOWN").

import os
import csv
import re
import shutil
import storage

OLD_ALL_WEEKS_FILE = "data/output/offers.csv"          # the old final file (all weeks in one file, before version 3)

# =====================================================================================================
# THE FINAL FILE - the same for every store
# =====================================================================================================
SIMPLE_COLUMNS = ["week", "store", "offer_start_date", "offer_end_date", "brand",
                  "product_name", "product_weight", "price_eur", "offer_applied", "app_or_card_price"]
RENAMED = {"kaufland_card_xtra": "app_or_card_price"}     # old column name -> new name (old files are renamed, not thrown away)
NOT_IN_DATA_FILES = ["regular_price_eur", "xtra_price_eur", "xtra"]     # often empty -> left out of both files


def price_text(value):
    """'9.0' -> '9.00' ,  '1.49' -> '1.49'  (always 2 decimals, like on the flyer)"""
    if value == "":
        return ""
    return f"{float(value):.2f}"


# no empty cells in the data files: an empty cell gets a default value
#   yes/no columns -> "no",  "nothing" numbers -> "0",  no label / no problem -> "none",  everything else -> "UNKNOWN"
DEFAULTS = {"app_or_card_price": "no", "offer_applied": "no", "discount_pct": "0", "deposit_eur": "0",
            "label": "none", "labels": "none", "problems": "none", "notes": "none", "verify_note": "none",
            "multi_buy": "1", "app_discount_pct": "0", "app_multi_buy": "1", "app_labels": "none"}


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


def read_rows(file_name):
    """all rows of a CSV file (an empty list if the file is not there)"""
    if not os.path.exists(file_name):
        return []
    with open(file_name, encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def save_with_replace(final_file, rows, columns):
    """Add rows to a final file. Old rows of the SAME FLYER are replaced, so a rerun never doubles.
    Same flyer = same week + store, OR same store + same last offer day (also catches a flyer saved under a wrong week).
    (In a weekly file this means: the store's rows of that week are replaced, the other store's rows are kept.)
    Old rows with broken dates (start after end, e.g. 2026-12-19 -> 2026-11-14) are removed.
    An old column name (kaufland_card_xtra) is renamed. If the file has other columns (older code), it is put aside."""
    new_keys = []              # (week, store) of the new flyers
    new_ends = []              # (store, last offer day) of the new flyers
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
            old_columns = csv.DictReader(file).fieldnames or []
        old_columns = [RENAMED.get(column, column) for column in old_columns]       # 'kaufland_card_xtra' -> 'app_or_card_price'
        if old_columns != columns:
            old_version = final_file.replace(".csv", "_old_version.csv")
            os.replace(final_file, old_version)                                    # put the old file aside
            print("Note:", final_file, "had other columns (older code) -> moved to", old_version, "- starting a new file")
    if os.path.exists(final_file):
        shutil.copy(final_file, final_file.replace(".csv", "_backup.csv"))     # safety copy
        with open(final_file, encoding="utf-8-sig") as file:
            for row in csv.DictReader(file):
                for old_name, new_name in RENAMED.items():
                    if old_name in row:
                        row[new_name] = row.pop(old_name)
                start, end = start_and_end(row)
                same_flyer = (row.get("week"), row.get("store")) in new_keys or (row.get("store"), end) in new_ends
                broken_dates = is_date(start) and is_date(end) and start > end
                if same_flyer or broken_dates:
                    replaced = replaced + 1          # replaced by the new rows (or removed: broken dates)
                else:
                    old_rows_kept.append(row)        # another flyer (another week or store) -> keep it
    all_rows = old_rows_kept + rows
    for row in all_rows:
        fill_empty(row, columns)
    with open(final_file, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerows(all_rows)
    return new_keys, len(old_rows_kept), replaced, len(all_rows)


# =====================================================================================================
# KAUFLAND: one verified row -> one row of the final file  (Kaufland's own helpers)
# =====================================================================================================
KAUFLAND_UNIT = r"(kg|g|ml|cl|l|Liter|Stück|St\.|ST|Blatt|Rollen|WL|m|Meter)(?![a-zäöüß])"
KAUFLAND_SIZE = r"(?:(\d+)\s?x\s?)?(\d+(?:[.,]\d+)?)(?:\s?-\s?(\d+(?:[.,]\d+)?))?\s?-?\s?" + KAUFLAND_UNIT
KAUFLAND_UNIT_NAMES = {"Liter": "l", "St.": "Stück", "ST": "Stück", "Meter": "m"}


def number_text(value):
    """'500.0' -> '500' ,  '0.7' -> '0.7' ,  '0,33' -> '0.33' ,  '1.000' (German thousands) -> '1000'"""
    value = str(value)
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", value):
        value = value.replace(".", "")
    number = float(value.replace(",", "."))
    if number == int(number):
        return str(int(number))
    return str(round(number, 3))


def kaufland_size_text(text):
    """the text after "je" -> the size in the style of the final file:
    '150-g-Becher' -> '150 g'     'Ka. 24 x 0,33-l-Fl.' -> '24 x 0.33 l'     '150 - 175-g-Packg.' -> '150-175 g'
    '8 St. = 240-g-Packg.' -> '240 g'     '16 - 36-St.-Packg.' -> '16-36 Stück'     '30-Blatt-Packg.' -> '30 Blatt'
    'Stück' -> 'Stück'     'Bund' -> 'Bund'     'kg' (sold by the kilo) -> '1 kg'     no size at all -> 'UNKNOWN'"""
    text = (text or "").replace("–", "-").replace("\xa0", " ")
    text = text.split("Abtropf")[0]                      # '540-g-Glas Abtropfgewicht 350 g' -> only the 540 g
    if "=" in text and re.search(KAUFLAND_SIZE, text.split("=")[-1]):
        text = text.split("=")[-1]                       # '8 St. = 240-g-Packg.' -> the weight after '='
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s?(?:kg|g|ml|l|Liter)\s?-\s?(?=\d)", r"\1-", text)   # '300 g - 400 g' -> '300-400 g'
    sizes = []
    for count, low, high, unit in re.findall(KAUFLAND_SIZE, text):
        size = number_text(low)
        if high:
            size = size + "-" + number_text(high)
        size = size + " " + KAUFLAND_UNIT_NAMES.get(unit, unit)
        if count:
            size = count + " x " + size
        if size not in sizes:
            sizes.append(size)
    if sizes:
        return "; ".join(sizes)                          # more than one size: '500 g; 2 x 250 g'
    if re.match(r"\s*kg\b", text):
        return "1 kg"
    for word in ["Stück", "Bund", "Paar"]:
        if word.lower() in text.lower():
            return word
    return "UNKNOWN"


def kaufland_weight(row):
    """The size as the flyer shows it: '500 g', '150-175 g', '24 x 0.33 l', 'Stück', '30 Blatt'"""
    unit = {"piece": "Stück"}.get(row["unit"], row["unit"])
    # a crate or multipack that verify.py repaired: "multipack 24 x 0.33 l"
    match = re.search(r"multipack (\d+) x ([\d.]+) (\w+)", row.get("verify_note", ""))
    if match:
        return match.group(1) + " x " + number_text(match.group(2)) + " " + match.group(3)
    # another size that verify.py found to fit the unit price: "28-g-Rollen bzw. 90-g-Packg." -> "90 g"
    if "fits the unit price" in row.get("verify_note", "") and row["pack_size"]:
        return number_text(row["pack_size"]) + " " + unit
    # everything else: the size written after "je" on the flyer
    weight = kaufland_size_text(row["weight"])
    if weight == "UNKNOWN" and row["pack_size"]:
        weight = number_text(row["pack_size"]) + " " + unit
    return weight


def kaufland(r):
    if r["regular_price_eur"] or r["discount_pct"] or r["label"] or r["xtra_price_eur"]:
        offer_applied = "yes"        # old price, -XX%, a label like KNÜLLER / AKTION, or an XTRA price
    else:
        offer_applied = "no"
    if r.get("xtra", "") == "yes":
        r["app_or_card_price"] = "yes"      # the flyer shows an extra price for Kaufland Card XTRA members
    else:
        r["app_or_card_price"] = "no"       # not mentioned -> "no" (never empty)
    if r["brand"].strip() == "":
        r["brand"] = "UNKNOWN"              # no brand in capitals on the flyer
    return {
        "week": r["week"],
        "store": r["store"],
        "offer_start_date": r["valid_from"],
        "offer_end_date": r["valid_to"],
        "brand": r["brand"],
        "product_name": r["product_name"],  # without the brand
        "product_weight": kaufland_weight(r),
        "price_eur": price_text(r["offer_price_eur"]),
        "offer_applied": offer_applied,
        "app_or_card_price": r["app_or_card_price"],
    }


# =====================================================================================================
# NETTO: one verified row -> one row of the final file  (Netto's own helpers)
# =====================================================================================================
NETTO_UNIT = r"(kg|g|ml|cl|l|Liter|Stück|St\.|ST|Blatt|Rollen|WL|m|Meter)(?![a-zäöüß])"
NETTO_SIZE = r"(?:(\d+)\s?x\s?)?(\d+(?:[.,]\d+)?)(?:\s?-\s?(\d+(?:[.,]\d+)?))?\s?-?\s?" + NETTO_UNIT
NETTO_UNIT_NAMES = {"Liter": "l", "St.": "Stück", "ST": "Stück", "Meter": "m"}


def netto_number_text(text):
    """'0,75' -> '0.75' ,  '500' -> '500' ,  '1,50' -> '1.5'"""
    number = float(text.replace(",", "."))
    if number == int(number):
        return str(int(number))
    return str(round(number, 3))


def netto_weight(text):
    """Netto's size text -> the size in the style of the final file:
    '0,75 Liter' -> '0.75 l'     '300 g – 400 g' -> '300-400 g'     '4 x 100 g' -> '4 x 100 g'
    '6 x 20 g; 3 x 45 g' -> the same     '1 kg' -> '1 kg'     'Stück' -> 'Stück'     'Bund' -> 'Bund'
    no size at all -> 'UNKNOWN'"""
    text = (text or "").replace("–", "-").replace("\xa0", " ").replace("\u202f", " ").replace("\u2009", " ")
    text = re.sub(r"(\d+(?:[.,]\d+)?)\s?(?:kg|g|ml|l|Liter)\s?-\s?(?=\d)", r"\1-", text)   # '300 g - 400 g' -> '300-400 g'
    sizes = []
    for count, low, high, unit in re.findall(NETTO_SIZE, text):
        size = netto_number_text(low)
        if high:
            size = size + "-" + netto_number_text(high)
        size = size + " " + NETTO_UNIT_NAMES.get(unit, unit)
        if count:
            size = count + " x " + size
        if size not in sizes:
            sizes.append(size)
    if sizes:
        return "; ".join(sizes)                          # more than one size: '6 x 20 g; 3 x 45 g'
    for word in ["Stück", "Bund", "Paar"]:
        if word.lower() in text.lower():
            return word
    return "UNKNOWN"


def netto(r):
    labels = r["labels"].split(", ")
    multi_buy = int(r["multi_buy"] or 1)
    if r["regular_price_eur"] or r["discount_pct"] or "Aktion" in labels or r["app_price_eur"] or multi_buy > 1:
        offer_applied = "yes"        # old price, -XX%, "Aktion", an app price or "2 für"  ("Dauertiefpreis" alone = normal price)
    else:
        offer_applied = "no"
    if r["app_price_eur"]:
        r["app_or_card_price"] = "yes"      # the flyer shows an extra price with the Netto app
    else:
        r["app_or_card_price"] = "no"
    return {
        "week": r["week"],
        "store": r["store"],
        "offer_start_date": r["valid_from"],
        "offer_end_date": r["valid_to"],
        "brand": "UNKNOWN",                 # Netto prints the brand inside the name: the name stays as printed
        "product_name": r["product_name"],
        "product_weight": netto_weight(r["weight"]),        # the same style as Kaufland
        "price_eur": price_text(r["offer_price_eur"]),
        "offer_applied": offer_applied,
        "app_or_card_price": r["app_or_card_price"],
    }


# =====================================================================================================
# RUN: every store of config/settings.yaml -> the final file of its week (all stores of a week in one file)
# (only when started as a program - python pipeline/load.py - not when the tests read this file)
# =====================================================================================================
if __name__ == "__main__":
    os.makedirs("data/output", exist_ok=True)
    STORE_PARTS = {"kaufland": kaufland, "netto": netto}

    # 0. ONE TIME: the old final file (all weeks in one file) is put aside - from now on there is one file per week
    if os.path.exists(OLD_ALL_WEEKS_FILE):
        os.makedirs("data/output/old", exist_ok=True)
        os.replace(OLD_ALL_WEEKS_FILE, "data/output/old/offers_all_weeks.csv")
        print("Note: the old", OLD_ALL_WEEKS_FILE, "(all weeks in one file) -> data/output/old/offers_all_weeks.csv",
              "- from now on: one file per week")

    # 1. every store: its good offers -> simple rows, sorted by week
    rows_of_week = {}            # '2026-W46' -> the simple rows of that week (all stores)
    counts = []
    for store in storage.stores():
        verified_file = "data/review/" + store + "/offers_verified.csv"
        rows = read_rows(verified_file)
        if store not in STORE_PARTS or len(rows) == 0:
            print(store + ": no new offers in this run (" + verified_file + ") - nothing to add")
            continue
        flyer_week = storage.current_week()          # for rows without a week: the week the pipeline is working on
        for r in rows:
            simple = STORE_PARTS[store](r)
            if not re.fullmatch(r"\d{4}-W\d\d", simple["week"]):
                simple["week"] = flyer_week
            rows_of_week.setdefault(simple["week"], []).append(simple)
        counts.append(store + ": " + str(len(rows)))
        # the detailed file of this store (all columns, except the often empty ones)
        detailed_columns = []
        for column in rows[0].keys():
            if column not in NOT_IN_DATA_FILES:
                detailed_columns.append(column)
        detailed_columns.append("app_or_card_price")
        save_with_replace("data/output/offers_detailed_" + store + ".csv", rows, detailed_columns)

    if len(rows_of_week) == 0:
        print("No new offers of any store - nothing to add (this week is already done, or no flyer).")
        exit()

    # 2. save: one final file per week. A store's rows of that week are replaced (a rerun never doubles),
    #    the other store's rows stay. The files of other weeks are not touched.
    print("New offers:", " | ".join(counts))
    for week in sorted(rows_of_week):
        week_file = storage.weekly_file(week)
        keys, kept, replaced, total = save_with_replace(week_file, rows_of_week[week], SIMPLE_COLUMNS)
        print("Week", week, "->", week_file, "| new rows:", len(rows_of_week[week]), "| rows of other stores kept:", kept,
              "| old rows replaced:", replaced, "| now", total, "offers")
    print("Done! One file per week in data/output (all details in data/output/offers_detailed_<store>.csv)")
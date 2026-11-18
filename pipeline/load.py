# load.py (stage 7 of 8) - adds this week's good offers to the weekly file
#
# How it works:
#   Every store turns its good offers into the same 10 columns, and all stores go into one file per week:
#   data/output/offers_2026-W47.csv. If a store runs again for that week, its old rows are replaced (nothing
#   is doubled) and the other stores stay. Only the offer price is saved. No cell is ever empty ("no" / "UNKNOWN").
#
# Tried and tuned:
#   - every store wrote the weight differently ("0,75 Liter", "200-g-Packg.", "2x100 g") -> one style: 0.75 l, 200 g, 2 x 100 g
#   - the 10th column was only for Kaufland (kaufland_card_xtra) -> app_or_card_price: Kaufland Card, Netto app, Lidl Plus
#   - one big file with all weeks, plus a detailed file -> one simple file per week

import os
import csv
import re
import storage

# =====================================================================================================
# THE WEEKLY FILE - the same for every store
# =====================================================================================================
SIMPLE_COLUMNS = ["week", "store", "offer_start_date", "offer_end_date", "brand",
                  "product_name", "product_weight", "price_eur", "offer_applied", "app_or_card_price"]
DEFAULTS = {"offer_applied": "no", "app_or_card_price": "no"}    # an empty yes/no cell -> "no", anything else -> "UNKNOWN"


def price_text(value):
    """'9.0' -> '9.00' ,  '1.49' -> '1.49'  (always 2 decimals, like on the flyer)"""
    if value == "":
        return ""
    return f"{float(value):.2f}"


def read_rows(file_name):
    """all rows of a CSV file (an empty list if the file is not there)"""
    if not os.path.exists(file_name):
        return []
    with open(file_name, encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def save_week(week_file, rows):
    """add the new rows of one week to its file: data/output/offers_2026-W47.csv
    The stores in the new rows lose their old rows in that file (so a rerun never doubles), the other stores stay.
    No cell is ever empty: an empty yes/no cell -> "no", anything else -> "UNKNOWN"."""
    new_stores = []
    for row in rows:
        if row["store"] not in new_stores:
            new_stores.append(row["store"])
    old_rows = [row for row in read_rows(week_file) if row["store"] not in new_stores]
    all_rows = old_rows + rows
    for row in all_rows:
        for column in SIMPLE_COLUMNS:
            if str(row.get(column, "") or "").strip() == "":
                row[column] = DEFAULTS.get(column, "UNKNOWN")
    with open(week_file, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=SIMPLE_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_rows)
    return len(old_rows), len(all_rows)


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
        app_or_card_price = "yes"           # the flyer shows an extra price for Kaufland Card XTRA members
    else:
        app_or_card_price = "no"
    return {
        "week": r["week"],
        "store": r["store"],
        "offer_start_date": r["valid_from"],
        "offer_end_date": r["valid_to"],
        "brand": r["brand"].strip() or "UNKNOWN",     # no brand in capitals on the flyer -> UNKNOWN
        "product_name": r["product_name"],  # without the brand
        "product_weight": kaufland_weight(r),
        "price_eur": price_text(r["offer_price_eur"]),
        "offer_applied": offer_applied,
        "app_or_card_price": app_or_card_price,
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
        app_or_card_price = "yes"           # the flyer shows an extra price with the Netto app
    else:
        app_or_card_price = "no"
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
        "app_or_card_price": app_or_card_price,
    }


# =====================================================================================================
# LIDL: one verified row -> one row of the final file  (Lidl's own helpers)
# =====================================================================================================
LIDL_NUMBER = r"\d+(?:,\d+|\.\d{1,2}(?!\d))?"                  # "100", "1,5", "12.5"  (but not "1.050")
LIDL_WEIGHT_SIZE = (r"(?:(\d+)\s?x\s?)?(" + LIDL_NUMBER + r"(?:\s?/\s?" + LIDL_NUMBER + r")*)\s?"
                    r"(kg|g|ml|cl|l|Liter|Stück|St\.|m|Meter|WL|Blatt|Rollen)(?![A-Za-zäöüß])")
LIDL_UNIT_NAMES = {"Liter": "l", "St.": "Stück", "Meter": "m"}


def lidl_number_text(text):
    """'1,75' -> '1.75' ,  '100' -> '100' ,  '12.5' -> '12.5'"""
    number = float(text.replace(",", "."))
    if number == int(number):
        return str(int(number))
    return str(round(number, 3))


def lidl_weight(text):
    """Lidl's weight text (written after "Je") -> the size in the style of the final file:
    '100 g' -> '100 g'     '1,75 l' -> '1.75 l'     '2x100 g' -> '2 x 100 g'     '80/100 g' -> '80/100 g'
    'ca. 580 g' -> 'ca. 580 g'     'Topf' -> 'Topf'     'Set' -> 'Set'     no size at all -> 'UNKNOWN'"""
    text = " ".join((text or "").split())
    if text == "":
        return "UNKNOWN"

    def one_size(match):
        count, numbers, unit = match.group(1), match.group(2), match.group(3)
        size = "/".join(lidl_number_text(number.strip()) for number in numbers.split("/"))
        size = size + " " + LIDL_UNIT_NAMES.get(unit, unit)
        if count:
            size = count + " x " + size
        return size

    return re.sub(LIDL_WEIGHT_SIZE, one_size, text)


def lidl(r):
    labels = r["labels"].split(", ")
    if r["old_price_eur"] or r["discount_pct"] or r["lidl_plus_price_eur"] or "Aktion" in labels:
        offer_applied = "yes"        # old price, -XX%, a Lidl Plus price, or "Aktion"
    else:
        offer_applied = "no"
    if r["lidl_plus_price_eur"]:
        app_or_card_price = "yes"           # the flyer shows an extra price with Lidl Plus (the Lidl app)
    else:
        app_or_card_price = "no"
    return {
        "week": r["week"],
        "store": r["store"],
        "offer_start_date": r["valid_from"],
        "offer_end_date": r["valid_to"],
        "brand": r["brand"] or "UNKNOWN",   # the CAPITAL words at the start of the name ("CHEF SELECT")
        "product_name": r["product_name"],  # without the brand
        "product_weight": lidl_weight(r["weight"]),     # the same style as Kaufland and Netto
        "price_eur": price_text(r["offer_price_eur"]),
        "offer_applied": offer_applied,
        "app_or_card_price": app_or_card_price,
    }


# =====================================================================================================
# RUN: every store of config/settings.yaml -> the final file of its week (all stores of a week in one file)
# (only when started as a program - python pipeline/load.py - not when the tests read this file)
# =====================================================================================================
if __name__ == "__main__":
    os.makedirs("data/output", exist_ok=True)
    STORE_PARTS = {"kaufland": kaufland, "netto": netto, "lidl": lidl}

    # 1. every store: its good offers -> rows of the weekly file, sorted by week
    rows_of_week = {}            # '2026-W47' -> the new rows of that week (all stores)
    counts = []
    for store in storage.stores():
        verified_file = "data/review/" + store + "/offers_verified.csv"
        rows = read_rows(verified_file)
        if store not in STORE_PARTS or len(rows) == 0:
            print(store + ": no new offers in this run (" + verified_file + ") - nothing to add")
            continue
        for r in rows:
            row = STORE_PARTS[store](r)
            if not re.fullmatch(r"\d{4}-W\d\d", row["week"]):
                row["week"] = storage.current_week()     # a row without a week: the week the pipeline is working on
            rows_of_week.setdefault(row["week"], []).append(row)
        counts.append(store + ": " + str(len(rows)))

    if len(rows_of_week) == 0:
        print("No new offers of any store - nothing to add (this week is already done, or no flyer).")
        exit()

    # 2. save: one file per week (the files of other weeks are not touched)
    print("New offers:", " | ".join(counts))
    for week in sorted(rows_of_week):
        week_file = storage.weekly_file(week)
        kept, total = save_week(week_file, rows_of_week[week])
        print("Week", week, "->", week_file, "| new rows:", len(rows_of_week[week]), "| rows of other stores kept:", kept,
              "| now", total, "offers")
    print("Done! One file per week in data/output")
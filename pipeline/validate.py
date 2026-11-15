# Stage 6: clean each offer and check if its numbers make sense  -  version 3: Kaufland + Netto
# Each store has its own function with its own checks (Netto uses nothing from the Kaufland part):
#   kaufland()  -> data/review/kaufland/offers_checked.csv
#   netto()     -> data/review/netto/offers_checked.csv
# At the bottom, every store in config/settings.yaml is run. If Netto fails, Kaufland still goes on.

import os
import csv
import re
import datetime
import storage


# =====================================================================================================
# KAUFLAND
# =====================================================================================================
# keyword -> category. The FIRST keyword found wins, so the order matters:
# e.g. "Thunfisch ... festes Fleisch" must hit "fisch" before "fleisch".
CATEGORY_KEYWORDS = [
    ("portion", "ready_meals"), ("eintopf", "ready_meals"), ("flammkuchen", "ready_meals"), ("germknödel", "ready_meals"),
    ("liqueur", "alcohol"), ("likör", "alcohol"), ("aperitif", "alcohol"), ("wein", "alcohol"), ("bier", "alcohol"), ("vol. %", "alcohol"),
    ("fisch", "fish"), ("lachs", "fish"),
    ("salami", "meat_sausage"), ("schinken", "meat_sausage"), ("wurst", "meat_sausage"), ("rind", "meat_sausage"),
    ("lamm", "meat_sausage"), ("kalb", "meat_sausage"), ("schwein", "meat_sausage"), ("hähnchen", "meat_sausage"), ("fleisch", "meat_sausage"),
    ("duschgel", "personal_care"), ("shampoo", "personal_care"), ("taschentücher", "personal_care"), ("zahnpasta", "personal_care"),
    ("papier", "household"), ("folie", "household"), ("reiniger", "household"),
    ("müsli", "breakfast_spreads"), ("flocken", "breakfast_spreads"), ("konfitüre", "breakfast_spreads"), ("honig", "breakfast_spreads"),
    ("milch", "dairy_cheese"), ("käse", "dairy_cheese"), ("joghurt", "dairy_cheese"), ("butter", "dairy_cheese"),
    ("cappuccino", "drinks"), ("kaffee", "drinks"), ("kakao", "drinks"), ("tee", "drinks"), ("saft", "drinks"), ("shot", "drinks"), ("wasser", "drinks"),
    ("kiwi", "fruit_vegetables"), ("paprika", "fruit_vegetables"), ("zuccini", "fruit_vegetables"), ("zucchini", "fruit_vegetables"),
    ("ingwer", "fruit_vegetables"), ("gemüse", "fruit_vegetables"), ("apfel", "fruit_vegetables"), ("tomate", "fruit_vegetables"),
    ("schoko", "snacks_sweets"), ("chips", "snacks_sweets"), ("keks", "snacks_sweets"),
    ("zucker", "baking_cooking"), ("mehl", "baking_cooking"), ("fett", "baking_cooking"), ("gewürz", "baking_cooking"),
    ("katzen", "pet_food"), ("hunde", "pet_food"),
]


def to_number(text):
    """'1.99' -> 1.99 ,  '' -> None"""
    if text == "":
        return None
    return float(text.strip("*"))     # "2.99*" -> 2.99 (the * is a footnote mark)


def matches(calculated, printed):
    """True if a calculated unit price is the printed one: 1% or 1 cent difference allowed (rounding)"""
    return abs(calculated - printed) <= max(printed * 0.01, 0.01)


# Kaufland's columns of the output file, in this order
KAUFLAND_COLUMNS = ["week", "store", "page", "origin", "brand", "product_name", "category", "weight", "pack_size", "unit",
                    "offer_price_eur", "regular_price_eur", "xtra_price_eur", "xtra", "discount_pct", "unit_price_eur", "unit_price_basis",
                    "unit_price_source", "deposit_eur", "label", "valid_from", "valid_to", "description", "check", "problems"]


def kaufland():
    """Kaufland: data/offers/kaufland/offers.csv -> data/review/kaufland/offers_checked.csv  (the code as before)"""
    STORE = "kaufland"
    input_file = "data/offers/kaufland/offers.csv"
    output_folder = "data/review/kaufland"
    os.makedirs(output_folder, exist_ok=True)

    clean_rows = []

    with open(input_file, encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            try:                      # if one offer causes an error, mark it and go on with the next one
                description = row["description"]
                problems = []

                # 1. prices and discount
                offer_price = to_number(row["offer_price"])
                regular_price = to_number(row["regular_price"])
                discount = to_number(row["discount_pct"])

                # 2. calendar week from the start date: 2026-11-09 -> 2026-W46
                week = ""
                if row["valid_from"]:
                    year, week_number, weekday = datetime.date.fromisoformat(row["valid_from"]).isocalendar()
                    week = str(year) + "-W" + str(week_number).zfill(2)

                # 3. pack size (only for food; non-food has no weight)
                pack_size, unit = None, ""
                after_je = row["weight"]                            # the text after "je", e.g. "200-g-Packg."
                match = re.search(r"([\d,]+)(?: - ([\d,]+))?[- ]?(kg|g|ml|l)\b", after_je)
                pieces = re.search(r"(\d+) x (\d+)-St", after_je)
                if row["page_type"] == "non_food":
                    pass
                elif match:                                         # "750-g", "0,7-l", "100 g", "120 - 150-g" (bigger one)
                    size_text = match.group(2) or match.group(1)
                    pack_size = float(size_text.replace(",", "."))
                    unit = match.group(3)
                elif after_je.startswith("kg"):                     # "je kg" (loose fruit and vegetables)
                    pack_size, unit = 1, "kg"
                elif pieces:                                        # "je 15 x 9-St.-Packg." = 135 pieces
                    pack_size, unit = int(pieces.group(1)) * int(pieces.group(2)), "piece"
                elif after_je.startswith("Stück") or after_je.startswith("Portion"):
                    pack_size, unit = 1, "piece"
                else:
                    problems.append("no pack size")

                # 4. drained weight: "Abtropfgewicht 250 g - 285 g" -> the unit price is for 285 g
                check_size = pack_size
                if "Abtropfgewicht" in description:
                    numbers = re.findall(r"\d+", description.split("Abtropfgewicht")[1].split("(")[0])
                    check_size = max(int(n) for n in numbers)

                # 5. size in kg or l (or pieces)
                size_in_base = None
                if pack_size:
                    if unit in ["g", "ml"]:
                        size_in_base = check_size / 1000
                    else:
                        size_in_base = check_size

                # 5b. Kaufland Card XTRA: the product has 2 prices, the normal price and a LOWER XTRA price
                #     (only for people with the paid Kaufland Card XTRA). We want:
                #     offer price = the normal price (everybody pays it), XTRA price in its own column.
                #     Example: prices 1.66 and 1.79, printed "(1 kg = 4.03)", 445 g:
                #     1.79 / 0.445 = 4.03 -> 1.79 is the normal price, 1.66 is the XTRA price
                xtra_price = None
                printed = re.search(r"1 (kg|l) = ([\d.]+)", row["unit_price"])      # "1 kg = 4.03"
                if row["xtra"] == "yes":
                    found = []                         # all prices found at this product, lowest first
                    for text in [row["offer_price"], row["regular_price"]] + row["other_prices"].split():
                        if text != "" and to_number(text) not in found:
                            found.append(to_number(text))
                    found.sort()
                    normal = None
                    if printed and size_in_base:       # the printed unit price says which one is the normal price
                        for price in found:
                            if matches(price / size_in_base, float(printed.group(2))):
                                normal = price
                    if normal is None and printed and size_in_base and discount is not None and found:
                        # the normal price was not found, but the flyer tells us TWICE what it is:
                        # unit price x size (7.98 x 0.5 l = 3.99) AND the old price -XX% (4.95 - 19% = 3.99)
                        guess = round(float(printed.group(2)) * size_in_base, 2)
                        old = found[-1]
                        if old > guess and abs(int((1 - guess / old) * 100) - discount) <= 1:
                            normal = guess
                            found.append(guess)
                            found.sort()
                            problems.append("normal price calculated from unit price and discount (not read)")
                    if normal is None and len(found) >= 2:
                        normal = found[1]              # no help from the unit price: 2nd lowest (the lowest is XTRA)
                    if found and found[0] != normal:
                        xtra_price = found[0]          # the lowest price is the XTRA price
                    regular_price = None               # old (crossed-out) price = the highest, above the normal price
                    for price in found:
                        if normal is not None and price > normal:
                            regular_price = price
                    offer_price = normal

                if offer_price is None and xtra_price is not None:
                    problems.append("no price (only the XTRA price " + str(xtra_price) + " was found)")
                elif offer_price is None:
                    problems.append("no price")

                # 6. unit price: printed "(1 kg = 3.59)", or calculated if the flyer does not print it
                unit_price, unit_price_basis, unit_price_source = None, "", ""
                if printed:
                    unit_price_basis = printed.group(1)
                    unit_price = float(printed.group(2))
                    unit_price_source = "printed"
                    # the check: price / size should be the printed unit price (1% or 1 cent for rounding)
                    if offer_price and size_in_base:
                        if not matches(offer_price / size_in_base, unit_price):
                            problems.append("price and unit price do not match")
                elif offer_price and size_in_base:
                    unit_price = round(offer_price / size_in_base, 2)
                    unit_price_basis = {"g": "kg", "kg": "kg", "ml": "l", "l": "l", "piece": "piece"}[unit]
                    unit_price_source = "calculated"

                # 7. check the discount: 1.29 instead of 1.69 is 23% off (allow 1 point for rounding)
                if regular_price and offer_price:
                    if regular_price <= offer_price:
                        problems.append("old price is not higher than offer price")
                    elif discount is not None:
                        calculated_discount = int((1 - offer_price / regular_price) * 100)
                        if abs(calculated_discount - discount) > 1:
                            problems.append("discount does not match prices")

                # 8. deposit: "(+ 0.25 Pfand)"
                match = re.search(r"\+ ([\d.]+) Pfand", description)
                deposit = float(match.group(1)) if match else None

                # 9. category: non-food pages first, then keywords
                category = "other"
                if row["page_type"] == "non_food":
                    category = "non_food"
                else:
                    text = (row["brand"] + " " + row["product_name"] + " " + description + " " + row["weight"]).lower()
                    for keyword, cat in CATEGORY_KEYWORDS:
                        if keyword in text:
                            category = cat
                            break

                # 10. result of the check
                check = "please check" if problems else "ok"

                clean_rows.append({
                    "week": week, "store": STORE, "page": row["page"],
                    "origin": row["origin"], "brand": row["brand"], "product_name": row["product_name"],
                    "category": category, "weight": row["weight"], "pack_size": pack_size, "unit": unit,
                    "offer_price_eur": offer_price, "regular_price_eur": regular_price, "xtra_price_eur": xtra_price,
                    "xtra": row["xtra"],
                    "discount_pct": row["discount_pct"],
                    "unit_price_eur": unit_price, "unit_price_basis": unit_price_basis, "unit_price_source": unit_price_source,
                    "deposit_eur": deposit, "label": row["label"],
                    "valid_from": row["valid_from"], "valid_to": row["valid_to"],
                    "description": description, "check": check, "problems": "; ".join(problems),
                })
                print(row["brand"], row["product_name"], "|", pack_size, unit, "|", offer_price, "|", category, "|", check)
            except Exception as error:
                clean_rows.append({"store": STORE, "page": row.get("page", ""), "brand": row.get("brand", ""),
                                   "product_name": row.get("product_name", ""), "check": "please check",
                                   "problems": "could not process this offer: " + str(error)})
                print("ERROR on page", row.get("page", ""), "-", row.get("product_name", ""), "->", error)

    # 11. save the clean table
    with open(output_folder + "/offers_checked.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=KAUFLAND_COLUMNS, restval="")     # restval: empty cell if a value is missing
        writer.writeheader()
        writer.writerows(clean_rows)

    ok_count = sum(1 for r in clean_rows if r["check"] == "ok")
    print("Done!", len(clean_rows), "offers:", ok_count, "ok,", len(clean_rows) - ok_count, "please check")


# =====================================================================================================
# NETTO - Netto's own checks (nothing from the Kaufland part):
#   price / size = the printed unit price "(2.38 / kg)"   (a range "(0.69 – 1.38 / l)" and "2 für" are allowed)
#   the old price ("UVP 0.99", "statt 1.19", crossed out) must be higher than the offer price
#   the -XX% must fit the old price and the offer price
#   offer price = the normal price; if only the app price is in a box: "Preis ohne App: 3.69", else the app price
# =====================================================================================================
# a size on the flyer: "150 g", "0,75 Liter", "4 x 100 g", "300 g – 400 g"
NETTO_NUMBER = r"\d+(?:,\d+)?"
NETTO_UNIT = r"(?:kg|g|ml|cl|l|Liter|Stück|ST|St\.|m|Meter|WL|Blatt|Rollen)(?![A-Za-zäöüß])"
# a unit price: "(2.38 / kg)", "(0.69 – 1.38 / l)", "(5.- / kg)", "(App: 4.52 / kg)"
NETTO_PRICE = r"\d+\.(?:\d\d|[-–])"
NETTO_UNIT_PRICE = (r"\((App:\s*)?(" + NETTO_PRICE + r")(?:\s*[–-]\s*(" + NETTO_PRICE + r"))?"
                    r"\s*/\s*(kg|l|m|WL|Stück)\s*(?:;[^)]*)?\)")


def netto_money(text):
    """'2.38' -> 2.38 ,  '5.-' -> 5.0 ,  '1.–' -> 1.0 ,  '1.299.-' -> 1299.0"""
    text = text.replace("–", "-")
    if text.endswith(".-") or text.endswith("."):
        text = text.rstrip("-").rstrip(".") + ".00"
    euros, cents = text.rsplit(".", 1)
    return float(euros.replace(".", "") + "." + cents)


def netto_sizes(weight):
    """'4 x 100 g' -> [(0.4, 'kg')] ,  '300 g – 400 g' -> [(0.3, 'kg'), (0.4, 'kg')] ,  'Stück' -> [(1, 'Stück')]
    every size the weight text can mean, in kg / l / m / Stück / WL (the units of the unit price)"""
    result = []
    for count, amount, unit in re.findall(r"(?:(\d+)\s?x\s?)?(" + NETTO_NUMBER + r")\s?(" + NETTO_UNIT + r")", weight):
        total = float(amount.replace(",", ".")) * (int(count) if count else 1)
        if unit == "g":
            result.append((total / 1000, "kg"))
        elif unit == "ml":
            result.append((total / 1000, "l"))
        elif unit == "cl":
            result.append((total / 100, "l"))
        elif unit in ["l", "Liter"]:
            result.append((total, "l"))
        elif unit in ["Stück", "ST", "St."]:
            result.append((total, "Stück"))
        elif unit == "Meter":
            result.append((total, "m"))
        else:
            result.append((total, unit))             # kg, m, WL
    # a range written as "150 - 175 g": the first number has no unit -> same unit as the second one
    for first, second, unit in re.findall(r"(" + NETTO_NUMBER + r")\s?[–-]\s?(" + NETTO_NUMBER + r")\s?(" + NETTO_UNIT + r")", weight):
        result = result + netto_sizes(first + " " + unit)
    if weight == "Stück":
        result.append((1, "Stück"))
    return result


def netto_unit_price_fits(price, weight, unit_price_text, multi=1):
    """True if price / size = a printed unit price (1% or 1 cent difference allowed for rounding)
    A range '(0.69 – 1.38 / l)' fits if any size gives any of the two numbers."""
    if price is None:
        return False
    for match in re.finditer(NETTO_UNIT_PRICE, unit_price_text):
        unit_prices = [netto_money(match.group(2))]
        if match.group(3):
            unit_prices.append(netto_money(match.group(3)))
        for size, unit in netto_sizes(weight):
            for times in sorted({1, multi}):              # "2 für 4.-": the price is for 2 packs
                if unit != match.group(4) or size * times <= 0:
                    continue
                for unit_price in unit_prices:
                    if abs(price / (size * times) - unit_price) <= max(unit_price * 0.01, 0.01):
                        return True
    return False


def netto_to_number(text):
    """'1.49' -> 1.49 ,  '' -> None"""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def netto_check(row):
    """the checks of one Netto offer -> (offer price, problems, notes)
    price / size = printed unit price, the old price is higher than the offer, the -XX% fits"""
    normal = netto_to_number(row["normal_price_eur"])
    app = netto_to_number(row["app_price_eur"])
    multi = max(int(row["multi_buy"] or 1), int(row["app_multi_buy"] or 1))
    problems, notes = [], []
    if normal is None and netto_to_number(row["price_without_app_eur"]) is not None:
        normal = netto_to_number(row["price_without_app_eur"])     # "Preis ohne App: 3.69" (only the app price is in a box)
        notes.append("price from 'Preis ohne App'")
    offer = normal if normal is not None else app
    if offer is None:
        problems.append("no price")
    if row["unit_price"] and offer is not None:
        if netto_unit_price_fits(offer, row["weight"], row["unit_price"], multi):
            notes.append("unit price fits")
        else:
            problems.append("price and unit price do not match")
    elif offer is not None:
        notes.append("not checked: no unit price printed")
    if app is not None and row["app_unit_price"] and not netto_unit_price_fits(app, row["weight"], row["app_unit_price"], multi):
        notes.append("WARNING app price and app unit price do not match")     # only a warning: the offer is the normal price
    old = netto_to_number(row["regular_price_eur"])                  # the old price at the normal price box
    discount = netto_to_number(row["discount_pct"])
    if old is not None and offer is not None:
        if old <= offer:
            problems.append("old price is not higher than offer price")
        elif discount is not None:
            percent = (1 - offer / old) * 100
            if min(abs(int(percent) - discount), abs(round(percent) - discount)) > 1:
                problems.append("discount does not match prices")
    return offer, problems, notes


NETTO_COLUMNS = ["week", "store", "page", "product_name", "weight", "unit_price", "app_unit_price",
                 "offer_price_eur", "normal_price_eur", "app_price_eur", "price_without_app_eur",
                 "regular_price_eur", "discount_pct", "multi_buy", "labels",
                 "app_discount_pct", "app_multi_buy", "app_labels",
                 "valid_from", "valid_to", "description", "check", "problems", "notes"]


def netto():
    """Netto: data/offers/netto/offers.csv -> data/review/netto/offers_checked.csv"""
    STORE = "netto"
    input_file = "data/offers/netto/offers.csv"
    output_folder = "data/review/netto"
    os.makedirs(output_folder, exist_ok=True)
    flyer_week = storage.current_week()                             # for a flyer without dates: the week we work on

    clean_rows = []
    with open(input_file, encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            try:                      # if one offer causes an error, mark it and go on with the next one

                # 1. calendar week from the start date: 2026-11-09 -> 2026-W46
                week = flyer_week
                if row["valid_from"]:
                    year, week_number, weekday = datetime.date.fromisoformat(row["valid_from"]).isocalendar()
                    week = str(year) + "-W" + str(week_number).zfill(2)

                r = {
                    "week": week, "store": STORE, "page": row["page"],
                    "product_name": row["product_name"], "weight": row["weight"],
                    "unit_price": row["unit_price"], "app_unit_price": row["app_unit_price"],
                    "normal_price_eur": row["price"], "app_price_eur": row["app_price"],
                    "price_without_app_eur": row["price_without_app"],
                    "regular_price_eur": row["regular_price"], "discount_pct": row["discount_pct"],
                    "multi_buy": row["multi_buy"], "labels": row["labels"],
                    "app_discount_pct": row["app_discount_pct"], "app_multi_buy": row["app_multi_buy"],
                    "app_labels": row["app_labels"],
                    "valid_from": row["valid_from"], "valid_to": row["valid_to"], "description": row["description"],
                }

                # 2. the checks: price / size = unit price, old price higher, the -XX% fits
                offer, problems, notes = netto_check(r)
                if r["product_name"] == "":
                    problems.append("no product name (a price box that no product took)")
                r["offer_price_eur"] = f"{offer:.2f}" if offer is not None else ""
                r["check"] = "please check" if problems else "ok"
                r["problems"] = "; ".join(problems)
                r["notes"] = "; ".join(notes)
                clean_rows.append(r)
                print(r["product_name"] or "(price without a product)", "|", r["weight"], "|", r["offer_price_eur"],
                      "|", r["check"])
            except Exception as error:
                clean_rows.append({"store": STORE, "page": row.get("page", ""), "product_name": row.get("product_name", ""),
                                   "check": "please check", "problems": "could not process this offer: " + str(error)})
                print("ERROR on page", row.get("page", ""), "-", row.get("product_name", ""), "->", error)

    # 3. save the clean table
    with open(output_folder + "/offers_checked.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=NETTO_COLUMNS, restval="")     # restval: empty cell if a value is missing
        writer.writeheader()
        writer.writerows(clean_rows)

    ok_count = sum(1 for r in clean_rows if r["check"] == "ok")
    print("Done!", len(clean_rows), "Netto rows:", ok_count, "ok,", len(clean_rows) - ok_count, "please check")


# =====================================================================================================
# RUN every store of config/settings.yaml with its own function (kaufland() and netto() above)
# (only when started as a program - python pipeline/validate.py - not when the tests read this file)
# =====================================================================================================
if __name__ == "__main__":
    STORE_PARTS = {"kaufland": kaufland, "netto": netto}
    for store in storage.stores():
        if store not in STORE_PARTS:
            print("\n" + store + ": validate.py has no function for this store yet - skipped")
            continue
        if not os.path.exists("data/offers/" + store + "/offers.csv"):
            print("\n" + store + ": no offers (no flyer, or an earlier stage failed) - skipped")
            continue
        print("\n----- " + store + " -----")
        try:
            STORE_PARTS[store]()
        except Exception as error:
            storage.store_failed(store, "validate", error)
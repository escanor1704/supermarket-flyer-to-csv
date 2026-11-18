# validate.py (stage 5 of 8) - cleans every offer and checks if its numbers make sense
#
# How it works:
#   The main check is the flyer's own maths: price / size = the printed unit price (1.99 for 500 g = 3.98 per kg).
#   The old price must be higher than the offer price, and the -XX% must fit both.
#   Every store has its own function, because each one prints these numbers differently.
#   -> data/review/<store>/offers_checked.csv  (check = ok / please check)
#
# Tried and tuned:
#   - flyers round their unit prices -> 1% or 1 cent difference is allowed
#   - Kaufland "15 x 9-St.-Packg." = 135 pieces -> pack sizes are multiplied out
#   - Netto prints ranges "(0.69 – 1.38 / l)" and "2 für" offers -> both can fit
#   - Lidl "Normalpreis: 2.49" next to a big Lidl Plus price -> the offer price is the Normalpreis

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
# LIDL - Lidl's own checks (nothing from the other parts):
#   price / size = the printed unit price "1 kg = 19.90"   (also "1 kg = 24.88/19.90" and "kg-Preis = 7.99")
#   the old price ("2.99" next to "-33%", "UVP 47.99") must be higher than the offer price, and the -XX% must fit
#   "Normalpreis: 2.49" next to a big Lidl Plus price -> the offer price is the Normalpreis
# =====================================================================================================
# a size: "100 g", "2x100 g", "12x 12.5 g", "1,75 l", "80 WL"   and a unit price: "1 kg = 19.90", "kg-Preis = 7.99"
LIDL_NUMBER = r"\d+(?:,\d+|\.\d{1,2}(?!\d))?"                  # "100", "1,5", "12.5"  (but not "1.050")
LIDL_UNIT = r"(?:kg|g|ml|cl|l|Liter|Stück|St\.|m|Meter|WL|Blatt|Rollen)(?![A-Za-zäöüß])"
LIDL_PRICE_VALUE = r"(?:\d+|[-–])\.\d\d"
LIDL_UNIT_PRICE = r"(\d+(?:,\d+)?)\s?(kg|g|l|ml|m|WL)\s?=\s?(" + LIDL_PRICE_VALUE + r"(?:\s?/\s?" + LIDL_PRICE_VALUE + r")*)"
LIDL_KG_PRICE = r"\b(kg|l|100-g)-Preis\s?=?\s?(\d+\.\d\d)"


def lidl_to_number(text):
    """'1.49' -> 1.49 ,  '' -> None"""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def lidl_price_value(text):
    """'19.90' -> 19.9 ,  '-.19' -> 0.19"""
    text = text.strip().replace("–", "-")
    if text.startswith("-."):
        text = "0" + text[1:]
    return float(text)


def lidl_sizes_of(text):
    """every '100 g', '2x100 g', '12x 12.5 g', '1,75 l', '80 WL' in a text -> [(0.1, 'kg'), (0.2, 'kg'), ...]"""
    result = []
    for count, amount, unit in re.findall(r"(?:(\d+)\s?x\s?)?(" + LIDL_NUMBER + r")\s?(" + LIDL_UNIT + r")", text):
        total = float(amount.replace(",", ".")) * (int(count) if count else 1)
        if unit == "g":
            result.append((total / 1000, "kg"))
        elif unit == "ml":
            result.append((total / 1000, "l"))
        elif unit == "cl":
            result.append((total / 100, "l"))
        elif unit in ["l", "Liter"]:
            result.append((total, "l"))
        else:
            result.append((total, unit))
    return result


def lidl_all_sizes(text):
    """EVERY size written in a description (the unit prices themselves are left out):
    'Je 80/100 g' -> 80 g and 100 g ,  'Je 1 kg; Abtropfgewicht: 900 g' -> 1 kg and 900 g ,  'Ca. 580 g' -> 580 g"""
    text = re.sub(LIDL_UNIT_PRICE, " ", text)
    text = re.sub(LIDL_KG_PRICE, " ", text)
    result = []
    for numbers, unit in re.findall(r"(\d+(?:,\d+)?(?:\s?/\s?\d+(?:,\d+)?)+)\s?(kg|g|ml|cl|l|WL)(?![A-Za-zäöüß])", text):
        for number in numbers.split("/"):
            result = result + lidl_sizes_of(number.strip() + " " + unit)     # "80/100 g": both numbers get the unit
    return result + lidl_sizes_of(text)


def lidl_unit_prices_of(text):
    """'1 kg = 19.90' -> [(1, 'kg', 19.9)] ,  '1 kg = 24.88/19.90' -> two ,  '1 WL = -.19' -> [(1, 'WL', 0.19)] ,
    'kg-Preis = 7.99' -> [(1, 'kg', 7.99)]"""
    result = []
    for amount, unit, values in re.findall(LIDL_UNIT_PRICE, text):
        base = float(amount.replace(",", "."))
        base_unit = unit
        if unit == "g":
            base, base_unit = base / 1000, "kg"
        elif unit == "ml":
            base, base_unit = base / 1000, "l"
        for value in values.split("/"):
            result.append((base, base_unit, lidl_price_value(value)))
    for kind, value in re.findall(LIDL_KG_PRICE, text):
        if kind == "100-g":
            result.append((0.1, "kg", float(value)))
        else:
            result.append((1.0, kind, float(value)))
    return result


def lidl_fits(price, sizes, unit_prices):
    """True if price / size = a printed unit price, for ANY size and ANY unit price (1% or 1 cent for rounding)"""
    if price is None:
        return False
    for base, base_unit, unit_price in unit_prices:
        for size, size_unit in sizes:
            if size_unit == base_unit and size > 0:
                if abs(price / size * base - unit_price) <= max(unit_price * 0.01, 0.01):
                    return True
    return False


def lidl_check(row):
    """the checks of one Lidl offer -> (offer price, old price, discount, problems, notes)
    With "Normalpreis: 2.49" Lidl prints the Lidl Plus price big: then the offer price is the Normalpreis
    (the price everybody pays) and the big price is the Lidl Plus price.
    When the unit price CONFIRMS the offer price, an old price / discount that does not fit came from a neighbour:
    it is removed (written in the notes) instead of sending the offer to review."""
    normal = lidl_to_number(row["normal_price_eur"])
    app = lidl_to_number(row["lidl_plus_price_eur"])
    if normal is not None:                                 # the old price and -XX% of the price box (normal box first)
        old, discount = lidl_to_number(row["normal_old_eur"]), lidl_to_number(row["normal_discount_pct"])
    elif app is not None:
        old, discount = lidl_to_number(row["lidl_plus_old_eur"]), lidl_to_number(row["lidl_plus_discount_pct"])
    else:
        old, discount = None, None
    sizes = lidl_all_sizes(row["description"]) + lidl_sizes_of(row["weight_box_size"])
    unit_prices = lidl_unit_prices_of(row["description"])
    problems = []
    notes = [note for note in row["structure_notes"].split("; ") if note]
    if normal is None and app is not None and "Normalpreis" in row["description"]:
        found = re.search(r"Normalpreis:?\s?(\d+\.\d\d)", row["description"])
        if found:
            normal = float(found.group(1))
        elif old is not None:
            normal, old = old, None                        # the number next to "Normalpreis:" was read as old price
        if normal is not None:
            notes.append("normal price from 'Normalpreis'")
        if old is not None and normal is not None and abs(old - normal) < 0.005:
            old = None                                     # the same number twice
    offer = normal if normal is not None else app
    confirmed = False
    if offer is None:
        problems.append("no price")
    if unit_prices and offer is not None:
        if lidl_fits(offer, sizes, unit_prices):
            notes.append("unit price fits")
            confirmed = True
        elif app is not None and lidl_fits(app, sizes, unit_prices):
            notes.append("unit price fits the Lidl Plus price")
            confirmed = True
        else:
            problems.append("price and unit price do not match")
    elif offer is not None:
        notes.append("not checked: no unit price printed")
    if old is not None and offer is not None:
        wrong = ""
        if old <= offer:
            wrong = "old price is not higher than offer price"
        elif discount is not None:
            percent = (1 - offer / old) * 100
            if min(abs(int(percent) - discount), abs(round(percent) - discount)) > 1:
                wrong = "discount does not match prices"
        if wrong and confirmed:
            removed = "old price " + f"{old:.2f}"
            if discount is not None:
                removed = removed + " and -" + str(int(discount)) + "%"
            notes.append(removed + " removed: " + wrong + " (the offer price fits the unit price)")
            old, discount = None, None
        elif wrong:
            problems.append(wrong)
    return offer, old, discount, problems, notes

LIDL_COLUMNS = ["week", "store", "page", "brand", "product_name", "weight", "unit_price",
                "offer_price_eur", "old_price_eur", "discount_pct",
                "normal_price_eur", "normal_old_eur", "normal_discount_pct", "normal_per", "normal_weight_box", "normal_colour",
                "lidl_plus_price_eur", "lidl_plus_old_eur", "lidl_plus_discount_pct", "weight_box_size", "labels",
                "valid_from", "valid_to", "description", "structure_notes", "price_candidates", "check", "problems", "notes"]


def lidl():
    """Lidl: data/offers/lidl/offers.csv -> data/review/lidl/offers_checked.csv"""
    STORE = "lidl"
    input_file = "data/offers/lidl/offers.csv"
    output_folder = "data/review/lidl"
    os.makedirs(output_folder, exist_ok=True)
    pipeline_week = storage.current_week()            # for a flyer without the footer "47/2026"

    clean_rows = []
    with open(input_file, encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            try:                      # if one offer causes an error, mark it and go on with the next one
                r = {}
                for column in LIDL_COLUMNS:
                    r[column] = row.get(column, "")
                r["store"] = STORE
                if not re.fullmatch(r"\d{4}-W\d\d", r["week"]):
                    r["week"] = pipeline_week

                # the checks: price / size = unit price, old price higher, the -XX% fits
                offer, old, discount, problems, notes = lidl_check(r)
                if r["product_name"] == "":
                    problems.append("no product name (a price box that no product took)")
                r["offer_price_eur"] = f"{offer:.2f}" if offer is not None else ""
                r["old_price_eur"] = f"{old:.2f}" if old is not None else ""
                r["discount_pct"] = str(int(discount)) if discount is not None else ""
                r["check"] = "please check" if problems else "ok"
                r["problems"] = "; ".join(problems)
                r["notes"] = "; ".join(notes)
                clean_rows.append(r)
                print((r["brand"] + " " + r["product_name"]).strip() or "(price without a product)", "|", r["weight"],
                      "|", r["offer_price_eur"], "|", r["check"])
            except Exception as error:
                clean_rows.append({"store": STORE, "page": row.get("page", ""), "product_name": row.get("product_name", ""),
                                   "check": "please check", "problems": "could not process this offer: " + str(error)})
                print("ERROR on page", row.get("page", ""), "-", row.get("product_name", ""), "->", error)

    # save the clean table
    with open(output_folder + "/offers_checked.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=LIDL_COLUMNS, restval="")     # restval: empty cell if a value is missing
        writer.writeheader()
        writer.writerows(clean_rows)

    ok_count = sum(1 for r in clean_rows if r["check"] == "ok")
    print("Done!", len(clean_rows), "Lidl rows:", ok_count, "ok,", len(clean_rows) - ok_count, "please check")


# =====================================================================================================
# RUN every store of config/settings.yaml with its own function (kaufland() and netto() above)
# (only when started as a program - python pipeline/validate.py - not when the tests read this file)
# =====================================================================================================
if __name__ == "__main__":
    STORE_PARTS = {"kaufland": kaufland, "netto": netto, "lidl": lidl}
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
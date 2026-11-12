# Stage 6: clean each offer and check if its numbers make sense  -  version 2

import os
import csv
import re
import datetime

STORE = "kaufland"
input_file = "data/offers/kaufland/offers.csv"
output_folder = "data/review/kaufland"
os.makedirs(output_folder, exist_ok=True)

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


# the columns of the output file, in this order
COLUMNS = ["week", "store", "page", "origin", "brand", "product_name", "category", "weight", "pack_size", "unit",
           "offer_price_eur", "regular_price_eur", "xtra_price_eur", "xtra", "discount_pct", "unit_price_eur", "unit_price_basis",
           "unit_price_source", "deposit_eur", "label", "valid_from", "valid_to", "description", "check", "problems"]

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
    writer = csv.DictWriter(file, fieldnames=COLUMNS, restval="")     # restval: empty cell if a value is missing
    writer.writeheader()
    writer.writerows(clean_rows)

ok_count = sum(1 for r in clean_rows if r["check"] == "ok")
print("Done!", len(clean_rows), "offers:", ok_count, "ok,", len(clean_rows) - ok_count, "please check")
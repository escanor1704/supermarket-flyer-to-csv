# verify.py (stage 6 of 8) - repairs what it can, sorts out what is not an offer, sets aside the rest
#
# How it works:
#   A wrong price usually belongs to a neighbour on the same page. The unit price says what the price MUST be,
#   so a fitting price from the same page is taken (or swapped). Then every row goes into one of 3 files:
#   offers_verified.csv (good -> the weekly file), needs_review.csv (you look at these), not_offers.csv (removed)
#
# Tried and tuned:
#   - a price is only taken from a neighbour whose own check failed, never from one whose price fits
#   - Kaufland: banners and single letters were read as products -> sorted out as "not an offer"
#   - Netto pages 44-47 are copies of 40-43 -> the same offer twice is removed
#   - Lidl: a wrong old price next to a price the unit price confirms is removed instead of sending it to review

import os
import csv
import re
import storage


# =====================================================================================================
# KAUFLAND
# =====================================================================================================
# problems that keep an offer OUT of the final file (other problems, like "no pack size", are only warnings)
BLOCKERS = ["no price", "not match", "not higher", "could not process"]


def number(text):
    """'2.69' -> 2.69 ,  '' -> None"""
    try:
        return float(text)
    except ValueError:
        return None


def size_in_kg_or_l(pack_size, unit):
    """750 g -> 0.75 ,  0.7 l -> 0.7 ,  pieces / unknown -> None"""
    if pack_size is None:
        return None
    if unit in ["g", "ml"]:
        return pack_size / 1000
    if unit in ["kg", "l"]:
        return pack_size
    return None


def matches_unit_price(price, size, unit_price):
    """2.69 / 0.75 kg = 3.59 -> True  (1% or 1 cent allowed for rounding)"""
    if not price or not size or not unit_price or size <= 0:
        return False                         # nothing to compare (and never divide by 0)
    return abs(price / size - unit_price) <= max(unit_price * 0.01, 0.01)


def can_give_price(row):
    """Only a row whose price is probably WRONG may give it away:
    a removed row (banner, letter), a row whose own unit price does not fit, or a row without a product name.
    A row whose only problem is 'no pack size' keeps its price - that price is probably right."""
    return (row["status"] == "not an offer" or "not match" in row["problems"]
            or row["product_name"].strip() == "")


def remove_problem(row, text):
    """take one problem out of the 'problems' column"""
    problems = [p for p in row["problems"].split("; ") if p and text not in p]
    row["problems"] = "; ".join(problems)


def add_note(row, text):
    row["verify_note"] = (row["verify_note"] + "; " + text) if row["verify_note"] else text


def kaufland():
    """Kaufland: data/review/kaufland/offers_checked.csv -> the 3 files  (the code as before)"""
    folder = "data/review/kaufland"
    input_file = folder + "/offers_checked.csv"

    # 1. read all checked offers
    with open(input_file, encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    if len(rows) == 0:
        print("No offers in", input_file, "- nothing to verify.")
        return
    columns = list(rows[0].keys()) + ["verify_note"]
    for r in rows:
        r["verify_note"] = ""

    # 2. sort out what is not an offer
    for r in rows:
        if r["check"] == "ok":
            r["status"] = "ok"
        elif "no price" in r["problems"] and "no pack size" in r["problems"]:
            r["status"] = "not an offer"         # banners like "AUF ALLE ARTIKEL", coupons, magazine ads
        elif r["product_name"].strip() == "" and len(r["brand"].strip()) <= 1:
            r["status"] = "not an offer"         # single letters like A, U, S (= "AUS DEUTSCHLAND" written vertically)
        else:
            r["status"] = "check"

    # 3. other sizes in the weight text. The first size is not always the right one:
    #    multipack "24 x 0,33-l-Fl." = 7.92 l,  "2 x 75 - 125-g-Packg." = 250 g,  "28-g-Rollen bzw. 90-g-Packg." = 90 g
    #    -> try every size: the one that fits the printed unit price is the right one
    multipacks = 0
    for r in rows:
        if r["status"] != "check" or "unit price do not match" not in r["problems"]:
            continue                             # only for "price and unit price do not match" (not for a wrong -XX%)
        price = number(r["offer_price_eur"])
        unit_price = number(r["unit_price_eur"])
        if not price or not unit_price or r["unit_price_source"] != "printed":
            continue                             # a calculated unit price always fits -> it cannot confirm anything
        # every size: (count, first number, second number of a range, unit), e.g. ("2", "75", "125", "g")
        for count, first, second, unit in re.findall(r"(?:(\d+) x )?([\d,]+)(?: - ([\d,]+))?[- ]?(kg|g|ml|l)\b", r["weight"]):
            one = float((second or first).replace(",", "."))      # a range: the bigger number
            total = round(int(count) * one, 3) if count else one
            if matches_unit_price(price, size_in_kg_or_l(total, unit), unit_price):
                r["pack_size"] = total
                r["unit"] = unit
                remove_problem(r, "unit price do not match")
                if count:
                    add_note(r, "multipack " + count + " x " + str(one) + " " + unit)
                else:
                    add_note(r, "size " + str(total) + " " + unit + " (fits the unit price)")
                multipacks = multipacks + 1
                break

    # 4. wrong or missing price: the printed unit price tells us what the price MUST be
    #    e.g. (1 kg = 3.98) and 500 g -> the price must be 1.99 -> look for 1.99 on the same page
    repaired_prices = 0
    for r in rows:
        if r["status"] != "check":
            continue
        if "not match" not in r["problems"] and "no price" not in r["problems"]:
            continue
        pack_size = number(str(r["pack_size"]))
        size = size_in_kg_or_l(pack_size, r["unit"])
        unit_price = number(r["unit_price_eur"])
        if not size or not unit_price:
            continue                             # nothing printed to calculate with
        for other in rows:
            if other is r or other["page"] != r["page"] or other["status"] == "ok" or not can_give_price(other):
                continue
            other_price = number(other["offer_price_eur"])
            if other_price and matches_unit_price(other_price, size, unit_price):
                # swap the whole price box (price, old price, discount, label) between the two rows
                for key in ["offer_price_eur", "regular_price_eur", "xtra_price_eur", "discount_pct", "label"]:
                    r[key], other[key] = other[key], r[key]
                remove_problem(r, "not match")
                remove_problem(r, "no price")
                giver = (other["brand"] + " " + other["product_name"]).strip() or "a banner"
                add_note(r, "price " + r["offer_price_eur"] + " taken from '" + giver + "' (confirmed by unit price)")
                repaired_prices = repaired_prices + 1
                # the other row now has our old price (or none): check it again
                other_price = number(other["offer_price_eur"])
                other_size = size_in_kg_or_l(number(str(other["pack_size"])), other["unit"])
                other_unit_price = number(other["unit_price_eur"])
                if other_price and other_size and other_unit_price and matches_unit_price(other_price, other_size, other_unit_price):
                    remove_problem(other, "not match")       # the swap fixed this row too
                    add_note(other, "price " + other["offer_price_eur"] + " corrected by swap (confirmed by unit price)")
                    repaired_prices = repaired_prices + 1
                if other["offer_price_eur"] == "" and "no price" not in other["problems"]:
                    other["problems"] = (other["problems"] + "; no price").strip("; ")
                if other["product_name"].strip() == "" and other["offer_price_eur"] == "":
                    other["status"] = "not an offer"     # a banner that gave its price away
                break

    # 5. final decision: no blocker left -> ok (warnings like "no pack size" stay as a note)
    #    a row WITHOUT a product name is never accepted automatically (it is usually a banner, e.g. "TROCKEN 3.99")
    accepted_with_warning = 0
    for r in rows:
        if r["status"] != "check":
            continue
        blockers = [b for b in BLOCKERS if b in r["problems"]]
        if r["product_name"].strip() == "":
            r["problems"] = (r["problems"] + "; no product name (banner?)").strip("; ")
            continue
        if not blockers:
            r["status"] = "ok"
            if r["problems"]:
                add_note(r, "accepted with warning: " + r["problems"])
                accepted_with_warning = accepted_with_warning + 1
            r["check"] = "ok"
            r["problems"] = ""

    # 6. save the three files
    groups = {"offers_verified.csv": "ok", "needs_review.csv": "check", "not_offers.csv": "not an offer"}
    counts = {}
    for file_name, status in groups.items():
        selected = [r for r in rows if r["status"] == status]
        counts[status] = len(selected)
        with open(folder + "/" + file_name, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(selected)

    ok_from_start = sum(1 for r in rows if r["status"] == "ok" and r["verify_note"] == "")
    print("DEEP VERIFICATION")
    print("  ok from the start:         ", ok_from_start)
    print("  repaired:                  ", multipacks + repaired_prices,
          " (multipacks / other size:", str(multipacks) + ", price found by unit price:", str(repaired_prices) + ")")
    print("  accepted with a warning:   ", accepted_with_warning, " (e.g. no pack size - the price itself is fine)")
    print("  not an offer (removed):    ", counts["not an offer"], " -> " + folder + "/not_offers.csv")
    print("  still needs review:        ", counts["check"], " -> " + folder + "/needs_review.csv")
    print("Done!", counts["ok"], "good offers saved in", folder + "/offers_verified.csv (these go into the final file)")


# =====================================================================================================
# NETTO - the same idea as Kaufland, with Netto's own helpers (nothing from the Kaufland part):
#   1. wrong or missing price: the printed unit price tells us what the price MUST be -> look for that price
#      on the same page: a price box that no product took, or the price of a product whose own check failed
#   2. final decision with Netto's checks (netto_check, the same as in validate.py); the same offer twice (pages 44-47 repeat 40-43) -> removed
#   3. the same 3 files as Kaufland in data/review/netto
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


def netto_add_note(row, text):
    row["verify_note"] = (row["verify_note"] + "; " + text) if row["verify_note"] else text


NETTO_PRICE_BOX = ["normal_price_eur", "regular_price_eur", "discount_pct", "multi_buy", "labels"]   # what moves in a swap


def netto():
    """Netto: data/review/netto/offers_checked.csv -> offers_verified.csv, needs_review.csv, not_offers.csv"""
    folder = "data/review/netto"
    input_file = folder + "/offers_checked.csv"

    # 1. read all checked offers
    with open(input_file, encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    if len(rows) == 0:
        print("No offers in", input_file, "- nothing to verify.")
        return
    columns = list(rows[0].keys()) + ["verify_note"]
    for r in rows:
        r["verify_note"] = ""

    # 2. wrong or missing price: the printed unit price tells us what the price MUST be
    #    e.g. (3.98 / kg) and 500 g -> the price must be 1.99 -> look for a 1.99 price box on the same page
    #    (only a price box nobody took, or the price of a product whose own check failed, may be taken)
    repaired_prices = 0
    for r in rows:
        if r["product_name"] == "" or r["unit_price"] == "" or "could not process" in r["problems"]:
            continue
        offer, problems, notes = netto_check(r)
        if "price and unit price do not match" not in problems and "no price" not in problems:
            continue
        for other in rows:
            if other is r or other["page"] != r["page"] or other["normal_price_eur"] == "":
                continue
            if other["product_name"] != "":
                other_offer, other_problems, other_notes = netto_check(other)
                if not other_problems:
                    continue                                  # the other product's own price fits: never take it
            price = netto_to_number(other["normal_price_eur"])
            if netto_unit_price_fits(price, r["weight"], r["unit_price"], int(other["multi_buy"] or 1)):
                for key in NETTO_PRICE_BOX:                         # swap the whole price box (price, old price, -XX%, labels)
                    r[key], other[key] = other[key], r[key]
                giver = other["product_name"] or "a price box without a product"
                netto_add_note(r, "price " + r["normal_price_eur"] + " taken from '" + giver + "' (confirmed by unit price)")
                repaired_prices = repaired_prices + 1
                break

    # 3. final decision for every row (the checks again, after the repairs)
    seen = []                  # (name, weight, price, dates) of the offers we already have
    for r in rows:
        if "could not process" in r["problems"]:
            r["status"] = "check"                             # validate.py could not read this row
            continue
        offer, problems, notes = netto_check(r)
        r["offer_price_eur"] = f"{offer:.2f}" if offer is not None else ""
        r["problems"] = "; ".join(problems)
        r["notes"] = "; ".join(notes)
        if r["product_name"] == "":
            r["status"] = "not an offer"                      # a price box that no product took
            netto_add_note(r, "a price without a product")
        elif offer is None and r["weight"] == "" and r["unit_price"] == "":
            r["status"] = "not an offer"                      # no price and no size: a banner or a coupon text
        elif problems:
            r["status"] = "check"
        else:
            r["status"] = "ok"
        key = (r["product_name"], r["weight"], r["offer_price_eur"], r["valid_from"], r["valid_to"])
        if r["status"] != "not an offer":
            if key in seen:
                r["status"] = "not an offer"                  # the same offer again (pages 44-47 repeat pages 40-43)
                netto_add_note(r, "the same offer is already on an earlier page")
            else:
                seen.append(key)
        r["check"] = "ok" if r["status"] == "ok" else "please check"

    # 4. save the three files
    groups = {"offers_verified.csv": "ok", "needs_review.csv": "check", "not_offers.csv": "not an offer"}
    counts = {}
    for file_name, status in groups.items():
        selected = [r for r in rows if r["status"] == status]
        counts[status] = len(selected)
        with open(folder + "/" + file_name, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(selected)

    confirmed = sum(1 for r in rows if r["status"] == "ok" and "unit price fits" in r["notes"])
    print("DEEP VERIFICATION (Netto)")
    print("  ok:                        ", counts["ok"], " (" + str(confirmed) + " confirmed by the unit price)")
    print("  repaired:                  ", repaired_prices, " (price found by unit price)")
    print("  not an offer (removed):    ", counts["not an offer"], " -> " + folder + "/not_offers.csv",
          "(banners, prices without a product, repeats)")
    print("  still needs review:        ", counts["check"], " -> " + folder + "/needs_review.csv")
    print("Done!", counts["ok"], "good offers saved in", folder + "/offers_verified.csv (these go into the final file)")


# =====================================================================================================
# LIDL - the same idea as Kaufland and Netto, with Lidl's own helpers (nothing from the other parts):
#   1. wrong or missing price: the printed unit price tells us what the price MUST be -> look for that price
#      on the same page: a price box that no product took, or the price of a product whose own check failed
#   2. final decision with Lidl's checks (lidl_check, the same as in validate.py); the same offer twice -> removed
#   3. the same 3 files as the other stores in data/review/lidl
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


def lidl_add_note(row, text):
    row["verify_note"] = (row["verify_note"] + "; " + text) if row["verify_note"] else text


LIDL_PRICE_BOX = ["normal_price_eur", "normal_old_eur", "normal_discount_pct", "normal_per", "normal_weight_box",
                  "normal_colour"]                         # what moves in a swap


def lidl():
    """Lidl: data/review/lidl/offers_checked.csv -> offers_verified.csv, needs_review.csv, not_offers.csv"""
    folder = "data/review/lidl"
    input_file = folder + "/offers_checked.csv"

    # 1. read all checked offers
    with open(input_file, encoding="utf-8-sig") as file:
        rows = list(csv.DictReader(file))
    if len(rows) == 0:
        print("No offers in", input_file, "- nothing to verify.")
        return
    columns = list(rows[0].keys()) + ["verify_note"]
    for r in rows:
        r["verify_note"] = ""

    # 2. wrong or missing price: the printed unit price tells us what the price MUST be
    #    e.g. "1 kg = 9.98" and "Je 200 g" -> the price must be 1.99 -> look for a 1.99 price on the same page
    #    (only a price box nobody took, or the price of a product whose own check failed, may be taken)
    repaired_prices = 0
    for r in rows:
        if r["product_name"] == "" or "could not process" in r["problems"]:
            continue
        unit_prices = lidl_unit_prices_of(r["description"])
        if not unit_prices:
            continue
        offer, old, discount, problems, notes = lidl_check(r)
        if "price and unit price do not match" not in problems and "no price" not in problems:
            continue
        sizes = lidl_all_sizes(r["description"]) + lidl_sizes_of(r["weight_box_size"])
        for other in rows:
            if other is r or other["page"] != r["page"] or other["normal_price_eur"] == "":
                continue
            if other["product_name"] != "":
                other_offer, other_old, other_discount, other_problems, other_notes = lidl_check(other)
                if not other_problems:
                    continue                                  # the other product's own price fits: never take it
            if lidl_fits(lidl_to_number(other["normal_price_eur"]), sizes, unit_prices):
                for key in LIDL_PRICE_BOX:                    # swap the whole price box (price, old price, -XX%, ...)
                    r[key], other[key] = other[key], r[key]
                giver = other["product_name"] or "a price box without a product"
                lidl_add_note(r, "price " + r["normal_price_eur"] + " taken from '" + giver + "' (confirmed by unit price)")
                repaired_prices = repaired_prices + 1
                break

    # 3. final decision for every row (the checks again, after the repairs)
    seen = []                  # (brand, name, weight, price, dates) of the offers we already have
    for r in rows:
        if "could not process" in r["problems"]:
            r["status"] = "check"                             # validate.py could not read this row
            r["check"] = "please check"
            continue
        offer, old, discount, problems, notes = lidl_check(r)
        r["offer_price_eur"] = f"{offer:.2f}" if offer is not None else ""
        r["old_price_eur"] = f"{old:.2f}" if old is not None else ""
        r["discount_pct"] = str(int(discount)) if discount is not None else ""
        r["problems"] = "; ".join(problems)
        r["notes"] = "; ".join(notes)
        if r["product_name"] == "":
            r["status"] = "not an offer"                      # a price box that no product took
            lidl_add_note(r, "a price without a product")
        elif offer is None and r["weight"] == "" and not lidl_unit_prices_of(r["description"]):
            r["status"] = "not an offer"                      # no price and no size: a headline or a coupon text
        elif any(word in r["problems"] for word in ["no price", "not match", "not higher"]):
            r["status"] = "check"
        else:
            r["status"] = "ok"
        key = (r["brand"], r["product_name"], r["weight"], r["offer_price_eur"], r["valid_from"], r["valid_to"])
        if r["status"] != "not an offer":
            if key in seen:
                r["status"] = "not an offer"                  # the same offer again
                lidl_add_note(r, "the same offer is already on an earlier page")
            else:
                seen.append(key)
        r["check"] = "ok" if r["status"] == "ok" else "please check"

    # 4. save the three files
    groups = {"offers_verified.csv": "ok", "needs_review.csv": "check", "not_offers.csv": "not an offer"}
    counts = {}
    for file_name, status in groups.items():
        selected = [r for r in rows if r["status"] == status]
        counts[status] = len(selected)
        with open(folder + "/" + file_name, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(selected)

    confirmed = sum(1 for r in rows if r["status"] == "ok" and "unit price fits" in r["notes"])
    with_brand = sum(1 for r in rows if r["status"] == "ok" and r["brand"])
    reasons = {}
    for r in rows:
        if r["status"] == "check":
            for problem in r["problems"].split("; "):
                reasons[problem] = reasons.get(problem, 0) + 1
    print("DEEP VERIFICATION (Lidl)")
    print("  ok:                        ", counts["ok"], " (" + str(confirmed) + " confirmed by the unit price,",
          with_brand, "with a brand)")
    print("  repaired:                  ", repaired_prices, " (price found by unit price)")
    print("  not an offer (removed):    ", counts["not an offer"], " -> " + folder + "/not_offers.csv",
          "(headlines, prices without a product, repeats)")
    print("  still needs review:        ", counts["check"], " -> " + folder + "/needs_review.csv", "| why:", reasons)
    print("Done!", counts["ok"], "good offers saved in", folder + "/offers_verified.csv (these go into the final file)")


# =====================================================================================================
# RUN every store of config/settings.yaml with its own function (kaufland() and netto() above)
# (only when started as a program - python pipeline/verify.py - not when the tests read this file)
# =====================================================================================================
if __name__ == "__main__":
    STORE_PARTS = {"kaufland": kaufland, "netto": netto, "lidl": lidl}
    for store in storage.stores():
        if store not in STORE_PARTS:
            print("\n" + store + ": verify.py has no function for this store yet - skipped")
            continue
        if not os.path.exists("data/review/" + store + "/offers_checked.csv"):
            print("\n" + store + ": no checked offers (no flyer, or an earlier stage failed) - skipped")
            continue
        print("\n----- " + store + " -----")
        try:
            STORE_PARTS[store]()
        except Exception as error:
            storage.store_failed(store, "verify", error)
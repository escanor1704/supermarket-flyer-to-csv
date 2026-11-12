# Stage 6b: deep verification
# Takes the offers that failed a check, tries to repair them, sorts out what is not an offer,
# and writes three files:
#   offers_verified.csv -> good offers (ok + repaired)  -> these go into the final file
#   needs_review.csv    -> still wrong, you look at these
#   not_offers.csv      -> banners, single letters, coupons (kept only so you can see what was removed)

import csv
import re

folder = "data/review/kaufland"
input_file = folder + "/offers_checked.csv"

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


# 1. read all checked offers
with open(input_file, encoding="utf-8-sig") as file:
    rows = list(csv.DictReader(file))
if len(rows) == 0:
    print("No offers in", input_file, "- nothing to verify.")
    exit()
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
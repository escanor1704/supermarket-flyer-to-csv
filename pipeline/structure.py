# Stage 5: group the text into offers (one row per product)  -  version 3
# NEW: we use how the text LOOKS on a Kaufland flyer:
#   product name  = bold font (Kaufland-Bold+), bigger    -> e.g. "Kalbshaxe"        (size 8 - 9)
#   weight        = same bold font, smaller, starts "je"   -> e.g. "je 100 g"         (size 6 - 7)
#   unit price    = the line under the weight              -> e.g. "(1 kg = 9.95)"
#   XTRA          = a 2nd, lower price for Kaufland Card XTRA members, marked "XTRA:" at the product
#   description   = normal font (Kaufland-Medium)          -> e.g. "in Scheiben,"
#   price         = heavy font (Kaufland-Heavy) INSIDE a box  (red box + white number, or white box + red number)

import os
import csv
import re
import datetime

input_folder = "data/text/kaufland"
output_folder = "data/offers/kaufland"
os.makedirs(output_folder, exist_ok=True)

TITLE_FONT = "Bold+"      # product name and weight line
TEXT_FONT = "Medium"      # description
PRICE_FONT = "Heavy"      # prices
LABELS = ["KNÜLLER", "AKTION", "PROBIERPREIS"]   # marketing words on top of a price box


def is_price(text):
    """True for '1.99' or '12.99*'"""
    return re.fullmatch(r"\d+\.\d\d\*?", text) is not None


def mostly_uppercase(text):
    """True if more than half of the letters are capitals, e.g. 'SAINT ALBRAY', "M&M's" """
    letters = [ch for ch in text if ch.isalpha()]
    capitals = [ch for ch in letters if ch.isupper()]
    return len(letters) > 0 and len(capitals) > len(letters) / 2


def join_words(words):
    """Join words into a sentence and repair words split over two lines:
    'Katzen-' + 'nahrung' -> 'Katzennahrung',  'Manuka-' + 'Honig' -> 'Manuka-Honig'"""
    result = []
    for word in words:
        if result and result[-1].endswith("­"):        # invisible soft hyphen: "WEIHEN­" + "STEPHAN"
            result[-1] = result[-1][:-1] + word
        elif result and len(result[-1]) > 1 and result[-1].endswith("-") and word not in ["und", "oder"]:
            before = result[-1]
            if word[:1].islower() or (mostly_uppercase(before) and mostly_uppercase(word)):
                result[-1] = before[:-1] + word      # remove the hyphen
            else:
                result[-1] = before + word           # keep the hyphen
        else:
            result.append(word)
    return " ".join(result)


def is_red(color):
    """'#ea1b27' -> True   (a lot of red, little green and blue)"""
    if len(color) != 7:
        return False
    red, green, blue = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    return red > 180 and green < 90 and blue < 90


def is_white(color):
    """'#ffffff' -> True"""
    if len(color) != 7:
        return False
    red, green, blue = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    return red > 240 and green > 240 and blue > 240


def middle(item):
    """the centre point of a text piece or a box"""
    return (item["left"] + item["right"]) / 2, (item["top"] + item["bottom"]) / 2


def is_inside(x, y, box):
    """True if the point (x, y) lies in the box (1 point extra on each side)"""
    return box["left"] - 1 <= x <= box["right"] + 1 and box["top"] - 1 <= y <= box["bottom"] + 1


def area(box):
    return (box["right"] - box["left"]) * (box["bottom"] - box["top"])


all_offers = []
page_summary = []      # one row per page: what was found and what was left over
dates = []             # every full date on the flyer: "09.11.2026"
weekday_dates = []     # dates written after a weekday: "MONTAG, 09.11." = the flyer's own dates -> (9, 11, "")

# go through the pages in order: page_1.csv, page_2.csv, ... (also works for page_10 and more)
page = 1
while os.path.exists(input_folder + "/page_" + str(page) + ".csv"):
    try:                          # if one page causes an error, note it and go on with the next page

        # 1. read the text pieces and the boxes of this page
        pieces = []
        with open(input_folder + "/page_" + str(page) + ".csv", encoding="utf-8-sig") as file:
            for row in csv.DictReader(file):
                for key in ["left", "top", "right", "bottom", "size"]:
                    row[key] = float(row[key])
                row["word"] = row["text"].strip()      # the text without spaces at the start and end
                row["used"] = False                    # True = already part of a price box
                pieces.append(row)

        price_boxes = []          # only boxes that can hold a price: red inside, white inside, or a red outline
        with open(input_folder + "/boxes_" + str(page) + ".csv", encoding="utf-8-sig") as file:
            for row in csv.DictReader(file):
                for key in ["left", "top", "right", "bottom"]:
                    row[key] = float(row[key])
                width = row["right"] - row["left"]
                height = row["bottom"] - row["top"]
                if 15 <= width <= 200 and 10 <= height <= 150:
                    if is_red(row["fill"]) or is_white(row["fill"]) or is_red(row["border"]):
                        price_boxes.append(row)

        # 2. page information: dates like 09.11.2026, and is this a non-food page?
        page_type = "food"
        for p in pieces:
            for date in re.findall(r"\d\d\.\d\d\.\d{4}", p["text"]):
                if date not in dates:
                    dates.append(date)
            weekday = r"(?:MONTAG|DIENSTAG|MITTWOCH|DONNERSTAG|FREITAG|SAMSTAG), (\d\d)\.(\d\d)\.(\d{4})?"
            for day, month, year in re.findall(weekday, p["text"].upper()):
                weekday_dates.append((int(day), int(month), year))      # "MONTAG, 09.11." -> (9, 11, "")
            if "_NF" in p["text"]:               # Kaufland prints a code like 6_D46-H_6130_NFgr1 on non-food pages
                page_type = "non_food"

        # 3. offer prices = heavy font, size 12 or bigger, looks like 1.99
        offer_prices = []
        for p in pieces:
            if PRICE_FONT not in p["font"] or p["size"] < 12 or not is_price(p["word"]):
                continue
            p["used"] = True
            # big prices are printed twice (red shadow + white number) -> keep only one
            duplicate = False
            for other in offer_prices:
                if other["word"] == p["word"] and abs(other["left"] - p["left"]) <= 3 and abs(other["top"] - p["top"]) <= 3:
                    duplicate = True
            if duplicate:
                continue
            # the price box = the SMALLEST box around the middle of the price
            x, y = middle(p)
            box = None
            for b in price_boxes:
                if is_inside(x, y, b) and (box is None or area(b) < area(box)):
                    box = b
            if box is None:                      # no box found -> use the price itself as its box
                box = {"left": p["left"], "top": p["top"], "right": p["right"], "bottom": p["bottom"]}
            p["box"] = box
            p["regular_price"] = ""
            p["other_prices"] = ""
            p["discount"] = ""
            p["label"] = ""
            p["xtra"] = False
            offer_prices.append(p)

        # 4. what belongs to each price: look INSIDE the box and in a strip just ABOVE it
        #    -23% -> discount,  KNÜLLER -> label,  XTRA -> a Kaufland Card XTRA price,
        #    smaller prices (1.69 or "UVP 29.99") -> old price, or the normal price next to an XTRA price
        #    small words inside the box (nur, ab, *) are taken out so they never end up in a product
        for price in offer_prices:
            box = price["box"]
            smaller_prices = []
            for p in pieces:
                if p["used"]:
                    continue
                x, y = middle(p)
                in_box = is_inside(x, y, box)
                above_box = box["left"] - 10 <= x <= box["right"] + 10 and box["top"] - 45 <= y <= box["top"]
                if not in_box and not above_box:
                    continue
                old_price = re.search(r"\d+\.\d\d", p["word"])
                if re.fullmatch(r"-\d+%", p["word"]):
                    price["discount"] = p["word"].strip("-%")
                    p["used"] = True
                elif p["word"] in LABELS:
                    price["label"] = p["word"]
                    p["used"] = True
                elif old_price and p["size"] < price["size"] and TEXT_FONT not in p["font"]:
                    smaller_prices.append(old_price.group())
                    p["used"] = True
                elif re.search(r"\bXTRA\b", p["word"]) and TITLE_FONT not in p["font"] and TEXT_FONT not in p["font"]:
                    price["xtra"] = True               # an XTRA mark at the price box
                    p["used"] = True
                elif in_box and TITLE_FONT not in p["font"] and TEXT_FONT not in p["font"]:
                    p["used"] = True                   # "nur", "ab", "*" (product text is never removed)
            # keep all smaller prices (validate.py needs them for XTRA products), and
            # the old (crossed-out) price = the HIGHEST smaller price that is higher than the offer price
            price["other_prices"] = " ".join(smaller_prices)
            for small in smaller_prices:
                if float(small) > float(price["word"].strip("*")):
                    if price["regular_price"] == "" or float(small) > float(price["regular_price"]):
                        price["regular_price"] = small

        # 5. make lines from the pieces that are left, and give every line a kind by its LOOK
        lines = {}
        for p in pieces:
            if p["used"]:
                continue
            key = (p["block"], p["line"])
            if key not in lines:
                lines[key] = []
            lines[key].append(p)

        line_list = []
        for line_pieces in lines.values():
            text = " ".join("".join(p["text"] for p in line_pieces).split())    # pieces -> one clean line
            main = line_pieces[0]                     # the piece with the most letters decides the look
            for p in line_pieces:
                if len(p["word"]) > len(main["word"]):
                    main = p
            if re.search(r"\bXTRA\b", text) and (TITLE_FONT in main["font"] or TEXT_FONT in main["font"]):
                kind = "xtra"              # Kaufland Card XTRA: "XTRA:" or "XTRA: (1 kg = 3.73)"
            elif TITLE_FONT in main["font"] and (text.startswith("je ") or text == "je"):
                kind = "weight"            # bold + small, starts with "je": "je 100 g"
            elif TITLE_FONT in main["font"] and 7.5 <= main["size"] <= 12:
                kind = "title"             # bold + big: the product name
            elif TITLE_FONT in main["font"] and main["size"] < 7.5:
                kind = "weight_more"       # bold + small, no "je": 2nd line of a weight ("9-St.-Packg.")
            elif TEXT_FONT in main["font"] and main["size"] <= 7.5:
                kind = "description"       # normal font: "in Scheiben,"  "(1 kg = 3.59)"
            else:
                kind = "other"             # banners, page code, small print -> not part of a product
            line_list.append({
                "text": text, "kind": kind, "used": False,
                "left": min(p["left"] for p in line_pieces), "right": max(p["right"] for p in line_pieces),
                "top": min(p["top"] for p in line_pieces), "bottom": max(p["bottom"] for p in line_pieces),
            })
        line_list.sort(key=lambda line: (line["top"], line["left"]))     # top to bottom, then left to right

        # 6. build the products: a product STARTS at a title line and takes the lines directly below it
        #    (same left edge, small gap): more title lines -> description -> "je ..." -> "(1 kg = 3.59)"
        products = []
        for start in line_list:
            if start["kind"] != "title" or start["used"]:
                continue
            group = [start]
            start["used"] = True
            last = start
            while True:
                next_line = None
                for line in line_list:
                    if line["used"] or line["kind"] == "other":
                        continue
                    same_left = abs(line["left"] - start["left"]) <= 3
                    gap = line["top"] - last["bottom"]
                    if same_left and -2 <= gap <= 4:
                        next_line = line
                        break
                if next_line is None:
                    break                          # nothing directly below -> the product ends here
                kinds = [line["kind"] for line in group]
                if next_line["kind"] == "title" and ("description" in kinds or "weight" in kinds):
                    break                          # a new title after the description = the NEXT product
                group.append(next_line)
                next_line["used"] = True
                last = next_line

            # keep it only if it really is a product: it has a "je" line,
            # or a brand in capitals + a description (non-food like "LIVARNO® Deko-Kissen")
            # (an ad like "kaufland.de/treueaktion" has neither -> not a product)
            kinds = [line["kind"] for line in group]
            if not ("weight" in kinds or ("description" in kinds and mostly_uppercase(group[0]["text"]))):
                continue

            # sort the lines into: origin / brand / name (title lines), weight, unit price, XTRA, description
            origin_words, brand_words, name_words, description_words = [], [], [], []
            weight_words, unit_price_words, xtra_words = [], [], []
            for line in group:
                words = line["text"].split()
                if line["kind"] == "weight" or (line["kind"] == "weight_more" and weight_words):
                    weight_words += words                    # bold "je" line: "je 200-g-Packg." (+ its 2nd line)
                elif line["kind"] == "xtra":
                    xtra_words += words                      # "XTRA: (1 kg = 3.73 - 5.36)"
                elif line["kind"] == "description" and re.match(r"\(1 (kg|l) =", line["text"]):
                    unit_price_words += words                # the line under it: "(1 kg = 9.95)"
                elif line["kind"] != "title":
                    description_words += words
                elif not brand_words and not name_words and len(words) == 1 and line["text"].endswith("."):
                    origin_words += words                    # e.g. "Span."  "Ital./griech."
                else:
                    # brand = the words in CAPITALS at the START of the bold title: "ORIGINAL WAGNER", "K-CLASSIC"
                    # "oder" / "&" between two capital words belongs to the brand: "SAINT ALBRAY oder CHAUMES"
                    # the rest of the title is the product name: "Die Backfrische oder Big City Pizza"
                    for position in range(len(words)):
                        word = words[position]
                        next_word = words[position + 1] if position + 1 < len(words) else ""
                        letters = [ch for ch in word if ch.isalpha()]
                        if name_words:
                            name_words.append(word)          # the name has started: everything else is name
                        elif mostly_uppercase(word) and (len(letters) >= 2 or position > 0):
                            brand_words.append(word)         # e.g. "WAGNER"  ("3D" at the start is no brand, "C" in "HOHES C" is)
                        elif word in ["oder", "und", "&", "+"] and brand_words and mostly_uppercase(next_word):
                            brand_words.append(word)         # e.g. "oder" in "MEZZO MIX oder LIFT"
                        else:
                            name_words.append(word)

            if not name_words:                           # the whole title is in capitals -> it is the name, no brand
                name_words = brand_words
                brand_words = []

            weight = join_words(weight_words)            # "je 200-g-Packg."
            if weight.startswith("je"):
                weight = weight[2:].strip()              # -> "200-g-Packg."  (the weight starts after "je")
            unit_price = join_words(unit_price_words).strip("()")     # "(1 kg = 9.95)" -> "1 kg = 9.95"
            xtra_unit_price = join_words(xtra_words).replace("XTRA:", "").replace("XTRA", "").strip(" ()")

            products.append({
                "origin": join_words(origin_words),
                "brand": join_words(brand_words),
                "product_name": join_words(name_words),
                "description": join_words(description_words),
                "weight": weight,
                "unit_price": unit_price,
                "xtra": len(xtra_words) > 0,                       # True = this product has an XTRA price
                "xtra_unit_price": xtra_unit_price,
                "left": min(line["left"] for line in group),       # left edge of the product text
                "right": max(line["right"] for line in group),     # right edge
                "bottom": max(line["bottom"] for line in group),   # bottom edge
                "price": None,
            })

        # 7. pair products and price boxes: closest pairs first, every price is used only once
        #    The price box sits where the product text ENDS (to the right or below),
        #    so we measure from the bottom-right corner of the text, and skip boxes on the left side.
        pairs = []
        for product in products:
            for price in offer_prices:
                box_x, box_y = middle(price["box"])
                if box_x < product["left"]:
                    continue
                distance = ((box_x - product["right"]) ** 2 + (box_y - product["bottom"]) ** 2) ** 0.5
                pairs.append((distance, products.index(product), offer_prices.index(price)))
        pairs.sort()
        used_prices = []
        for distance, product_number, price_number in pairs:
            product = products[product_number]
            if product["price"] is None and price_number not in used_prices:
                product["price"] = offer_prices[price_number]
                used_prices.append(price_number)

        # 8. one row per product
        for product in products:
            p = product["price"]
            has_xtra = product["xtra"] or (p is not None and p["xtra"])     # "XTRA" at the product text or at its price box
            all_offers.append({
                "page": page,
                "page_type": page_type,
                "origin": product["origin"],
                "brand": product["brand"],
                "product_name": product["product_name"],
                "description": product["description"],
                "weight": product["weight"],
                "unit_price": product["unit_price"],
                "xtra": "yes" if has_xtra else "",
                "xtra_unit_price": product["xtra_unit_price"],
                "offer_price": p["word"].strip("*") if p else "",
                "regular_price": p["regular_price"] if p else "",
                "other_prices": p["other_prices"] if p else "",
                "discount_pct": p["discount"] if p else "",
                "label": p["label"] if p else "",
            })
            print("Page", page, "-", product["brand"], product["product_name"], "->", p["word"] if p else "NO PRICE")

        # 9. leftovers on this page: prices nobody took (missed product?) and products without a price
        unpaired_prices = []
        for i in range(len(offer_prices)):
            if i not in used_prices:
                unpaired_prices.append(offer_prices[i]["word"])
        no_price = 0
        for product in products:
            if product["price"] is None:
                no_price = no_price + 1
        page_summary.append({
            "page": page,
            "page_type": page_type,
            "products": len(products),
            "prices": len(offer_prices),
            "products_without_price": no_price,
            "unpaired_prices": " ".join(unpaired_prices),
            "error": "",
        })

    except Exception as error:
        page_summary.append({"page": page, "page_type": "", "products": 0, "prices": 0,
                             "products_without_price": 0, "unpaired_prices": "", "error": str(error)})
        print("ERROR on page", page, "->", error)

    page = page + 1

# 10. dates of the flyer
#     Kaufland writes them after a weekday: "MONTAG, 09.11." on many pages, once with the year "SAMSTAG, 14.11.2026"
#     from = the weekday date written MOST OFTEN (the start of the offers)
#     to   = the latest weekday date in the 7 days after it
#     other dates ("Treueaktion vom 12.11.2026 bis 10.02.2027", "19.12.2026") are not used
year = ""
for day, month, y in weekday_dates:
    if y and year == "":
        year = y                               # the year from "SAMSTAG, 14.11.2026"
if year == "" and dates:
    year = dates[0][6:10]                      # or from any full date in the flyer
offer_days = []
if year:
    for day, month, y in weekday_dates:
        try:
            offer_days.append(datetime.date(int(y or year), month, day))
        except ValueError:
            pass                               # not a real date, e.g. "DONNERSTAG, 44.44." (a placeholder)
valid_from, valid_to = "", ""
if offer_days:
    start = max(offer_days, key=offer_days.count)      # the date written most often
    end = start
    for day in offer_days:
        if 0 <= (day - start).days <= 7 and day > end:
            end = day
    valid_from, valid_to = start.isoformat(), end.isoformat()      # 2026-11-09, 2026-11-14
elif len(dates) >= 2:                          # no weekday dates at all: first two dates, earlier one first
    first_two = sorted([dates[0][6:10] + "-" + dates[0][3:5] + "-" + dates[0][0:2],
                        dates[1][6:10] + "-" + dates[1][3:5] + "-" + dates[1][0:2]])
    valid_from, valid_to = first_two[0], first_two[1]
for offer in all_offers:
    offer["valid_from"] = valid_from
    offer["valid_to"] = valid_to

# 11. save all offers in one file
if len(all_offers) == 0:
    print("No offers found on any page - check the pages listed above.")
    exit(1)
with open(output_folder + "/offers.csv", "w", newline="", encoding="utf-8-sig") as file:
    writer = csv.DictWriter(file, fieldnames=all_offers[0].keys())
    writer.writeheader()
    writer.writerows(all_offers)

# 12. save the page summary (used by evaluate.py)
with open(output_folder + "/page_summary.csv", "w", newline="", encoding="utf-8-sig") as file:
    writer = csv.DictWriter(file, fieldnames=page_summary[0].keys())
    writer.writeheader()
    writer.writerows(page_summary)

print("Done!", len(all_offers), "offers saved in", output_folder + "/offers.csv")
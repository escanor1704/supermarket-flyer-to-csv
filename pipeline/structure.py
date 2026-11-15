# Stage 5: group the text into offers (one row per product)  -  version 4: Kaufland + Netto
# We use how the text LOOKS on the flyer. Each flyer has its own structure, so each store has its own function
# with its own helpers (Netto uses nothing from the Kaufland part, and Kaufland nothing from the Netto part):
#   kaufland()  -> data/offers/kaufland/offers.csv + page_summary.csv
#   netto()     -> data/offers/netto/offers.csv    + page_summary.csv
# At the bottom, every store in config/settings.yaml is run. If Netto fails, Kaufland still goes on.

import os
import csv
import re
import datetime
import storage


# =====================================================================================================
# KAUFLAND - how the text LOOKS on a Kaufland flyer:
#   product name  = bold font (Kaufland-Bold+), bigger    -> e.g. "Kalbshaxe"        (size 8 - 9)
#   weight        = same bold font, smaller, starts "je"   -> e.g. "je 100 g"         (size 6 - 7)
#   unit price    = the line under the weight              -> e.g. "(1 kg = 9.95)"
#   XTRA          = a 2nd, lower price for Kaufland Card XTRA members, marked "XTRA:" at the product
#   description   = normal font (Kaufland-Medium)          -> e.g. "in Scheiben,"
#   price         = heavy font (Kaufland-Heavy) INSIDE a box  (red box + white number, or white box + red number)
# =====================================================================================================
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


def kaufland():
    """Kaufland: text pieces + boxes -> data/offers/kaufland/offers.csv + page_summary.csv  (the code as before)"""
    input_folder = "data/text/kaufland"
    output_folder = "data/offers/kaufland"
    os.makedirs(output_folder, exist_ok=True)

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


# =====================================================================================================
# NETTO - how the text LOOKS on a Netto flyer  (everything here is Netto's own: nothing from the Kaufland part)
#   product name  = FrankfurterEF font, size 8.5 - 15           -> "Knorr Suppenliebe Suppe"
#   description   = HelveticaNeue font, smaller, under the name -> "versch. Sorten", "0,5 Liter - 1 Liter"
#   unit price    = HelveticaNeue, in brackets                  -> "(0.69 - 1.38 / l)",  "(App: 4.52 / kg)"
#   price         = FrankfurterEF, BIG euros + smaller cents    -> "0." + "69" = 0.69   (inside a drawn box)
#   app price     = the same, but PINK, with "+APP" on top      -> the price with the Netto app
#   old price     = small FrankfurterEF at the price box        -> "UVP 0.99",  "statt 1.19",  a CROSSED-OUT "4.99"
#   discount      = "-30%" in the yellow box above the price
#   dates         = on every page: "Montag 09.11. - Samstag 14.11.26", "Donnerstag 12.11. - ...", "Dienstag, 10.11.2026"
# =====================================================================================================
NETTO_NAME_FONT = "Frankfurter"      # product names, prices, labels
NETTO_TEXT_FONT = "Helvetica"        # description, weight, unit price
NETTO_PINK = "#ee4d9b"               # colour of the app price
NETTO_LABELS = ["Aktion", "Dauertiefpreis", "XXL", "+APP", "SPAREN", "pro kg", "pro Stück"]
NETTO_WEEKDAYS = "Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag"

# a size on the flyer: "150 g", "0,75 Liter", "4 x 100 g", "300 g – 400 g", "6 x 20 g; 3 x 45 g", "20 Stück; 8 m"
NETTO_NUMBER = r"\d+(?:,\d+)?"
NETTO_UNIT = r"(?:kg|g|ml|cl|l|Liter|Stück|ST|St\.|m|Meter|WL|Blatt|Rollen)(?![A-Za-zäöüß])"
NETTO_AMOUNT = r"(?:\d+\s?x\s?)?" + NETTO_NUMBER + r"\s?" + NETTO_UNIT
NETTO_SIZE = (r"(?:" + NETTO_NUMBER + r"\s?[–-]\s?)?" + NETTO_AMOUNT + r"(?:\s?[–-]\s?" + NETTO_AMOUNT + r")?"
              r"(?:;\s?" + NETTO_AMOUNT + r")*")
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


def netto_is_inside(x, y, box):
    """True if the point (x, y) lies in the box (1 point extra on each side)"""
    return box["left"] - 1 <= x <= box["right"] + 1 and box["top"] - 1 <= y <= box["bottom"] + 1


def netto_area(box):
    return (box["right"] - box["left"]) * (box["bottom"] - box["top"])


def netto_clean(text):
    """thin spaces -> normal spaces, invisible soft hyphens removed, '5. –' -> '5.–' """
    text = text.replace(" ", " ").replace(" ", " ").replace("\xa0", " ").replace("\xad", "")
    return re.sub(r"(\d\.) +([–-])", r"\1\2", text)


def netto_distance(a, b):
    """distance between two boxes (0 if they touch or overlap)"""
    dx = max(0, a["left"] - b["right"], b["left"] - a["right"])
    dy = max(0, a["top"] - b["bottom"], b["top"] - a["bottom"])
    return (dx ** 2 + dy ** 2) ** 0.5


def netto_join_lines(lines):
    """join lines and repair words split over two lines: 'Schoko-' + 'bons' -> 'Schokobons'"""
    result = ""
    for line in lines:
        line = line.strip()
        if result.endswith("-") and line[:1].islower() and line.split()[0] not in ["und", "oder"]:
            result = result[:-1] + line              # "Schoko-" + "bons"
        elif result.endswith("-") or result == "":
            result = result + line                   # "Deo-" + "spray" keeps no space,  first line
        else:
            result = result + " " + line
    return " ".join(result.split())


def netto_money_text(value):
    """1.5 -> '1.50' ,  None -> ''"""
    if value is None:
        return ""
    return f"{value:.2f}"


def netto_row(page, product, box, app_box, page_dates):
    """one row of data/offers/netto/offers.csv: the product text + its price box + its app price box
    (product None = a price box that no product took - verify.py may still give it to a product)"""
    if product is None:
        product = {"name": "", "description": "", "weight": "", "unit_price": "", "app_unit_price": "",
                   "price_without_app": None}
    return {
        "page": page,
        "product_name": product["name"],
        "description": product["description"],
        "weight": product["weight"],
        "unit_price": product["unit_price"],
        "app_unit_price": product["app_unit_price"],
        "price_without_app": netto_money_text(product["price_without_app"]),
        "price": netto_money_text(box["value"]) if box else "",
        "regular_price": netto_money_text(box["old"]) if box else "",
        "discount_pct": box["discount"] if box and box["discount"] is not None else "",
        "multi_buy": box["multi"] if box and box["multi"] > 1 else "",
        "labels": ", ".join(box["labels"]) if box else "",
        "app_price": netto_money_text(app_box["value"]) if app_box else "",
        "app_discount_pct": app_box["discount"] if app_box and app_box["discount"] is not None else "",
        "app_multi_buy": app_box["multi"] if app_box and app_box["multi"] > 1 else "",
        "app_labels": ", ".join(app_box["labels"]) if app_box else "",
        "page_dates": page_dates,              # -> valid_from / valid_to after the last page (step 9)
    }


def netto():
    """Netto: text pieces + boxes + thin lines -> data/offers/netto/offers.csv + page_summary.csv"""
    input_folder = "data/text/netto"
    output_folder = "data/offers/netto"
    os.makedirs(output_folder, exist_ok=True)
    all_offers = []        # one row per product (+ one row per price box that no product took)
    page_summary = []      # one row per page: what was found and what was left over
    flyer_dates = []       # (start, end) of every page that prints its dates

    page = 1
    while os.path.exists(input_folder + "/page_" + str(page) + ".csv"):
        try:                          # if one page causes an error, note it and go on with the next page

            # 1. read the text pieces, the boxes and the thin lines of this page (made by ocr.py)
            pieces = []
            with open(input_folder + "/page_" + str(page) + ".csv", encoding="utf-8-sig") as file:
                for row in csv.DictReader(file):
                    for key in ["left", "top", "right", "bottom", "size"]:
                        row[key] = float(row[key])
                    row["word"] = netto_clean(row["text"]).strip()
                    row["used"] = False
                    pieces.append(row)
            boxes = []              # price boxes, discount boxes, ...
            with open(input_folder + "/boxes_" + str(page) + ".csv", encoding="utf-8-sig") as file:
                for row in csv.DictReader(file):
                    for key in ["left", "top", "right", "bottom"]:
                        row[key] = float(row[key])
                    if 15 <= row["right"] - row["left"] <= 200 and 10 <= row["bottom"] - row["top"] <= 150:
                        boxes.append(row)
            strike_lines = []       # thin lines: an old price is CROSSED OUT with such a line
            with open(input_folder + "/lines_" + str(page) + ".csv", encoding="utf-8-sig") as file:
                for row in csv.DictReader(file):
                    for key in ["left", "top", "right", "bottom"]:
                        row[key] = float(row[key])
                    strike_lines.append(row)

            # 2. the dates of this page: "Montag 09.11. – Samstag 14.11.26" or one day "Dienstag, 10.11.2026"
            #    (a page can hold more than one: page 18 also has an old hidden "Montag 10.08. – Freitag 14.08.26"
            #     -> all are kept, step 9 takes the one that fits the flyer's week)
            page_dates = []
            for p in pieces:
                found = re.findall(r"(?:" + NETTO_WEEKDAYS + r"),? (\d\d)\.(\d\d)\.(\d{2,4})?", p["word"])
                years = [y for d, m, y in found if y]
                if not years:
                    continue
                year = 2000 + int(years[-1][-2:])                  # "26" or "2026" -> 2026
                try:
                    days = [datetime.date(year, int(m), int(d)) for d, m, y in found]
                except ValueError:
                    continue                                       # not a real date
                if days[0] > days[-1]:
                    days[0] = days[0].replace(year=year - 1)       # "Montag 29.12. – Samstag 03.01.27": start is in 2026
                page_dates.append((days[0], days[-1]))
            flyer_dates = flyer_dates + page_dates

            # 3. prices: BIG euros "1." (size 20 or more) + the smaller cents "49" right next to it (same colour)
            prices = []
            for p in pieces:
                if NETTO_NAME_FONT not in p["font"] or p["size"] < 20 or p["used"]:
                    continue
                match = re.fullmatch(r"(\d{1,3}(?:\.\d{3})*)\.([-–]*)", p["word"])
                if match is None:
                    continue
                cents = "00" if match.group(2) else None          # "1.–" = 1.00
                for c in pieces:
                    if cents is None and not c["used"] and c is not p and c["color"] == p["color"] and c["size"] < p["size"] \
                            and p["right"] - p["size"] * 0.35 <= c["left"] <= p["right"] + 4 \
                            and p["top"] - 3 <= c["top"] <= (p["top"] + p["bottom"]) / 2:     # (bigger price -> more overlap)
                        if re.fullmatch(r"\d\d", c["word"]):
                            cents = c["word"]
                            c["used"] = True
                        elif re.fullmatch(r"[-–]+", c["word"]):
                            cents = "00"
                            c["used"] = True
                if cents is None:
                    continue
                p["used"] = True
                value = float(match.group(1).replace(".", "") + "." + cents)          # "1.799." + "–" -> 1799.00
                duplicate = any(abs(q["left"] - p["left"]) < 3 and abs(q["top"] - p["top"]) < 3 for q in prices)
                if duplicate:
                    continue
                # the price box = the SMALLEST drawn box around the middle of the price
                x, y = (p["left"] + p["right"]) / 2, (p["top"] + p["bottom"]) / 2
                box = None
                for b in boxes:
                    if netto_is_inside(x, y, b) and (box is None or netto_area(b) < netto_area(box)):
                        box = b
                if box is None:
                    box = {"left": p["left"], "top": p["top"], "right": p["right"] + 20, "bottom": p["bottom"]}
                prices.append({"value": value, "app": p["color"] == NETTO_PINK, "size": p["size"],
                               "left": box["left"], "top": box["top"], "right": box["right"], "bottom": box["bottom"],
                               "old": None, "discount": None, "labels": [], "multi": 1, "owner": None})

            # 4. small things around a price box: "-30%", old price "UVP 0.99", labels "Aktion", "+APP", "2 für"
            #    each one goes to the NEAREST price box (at most 30 points away)
            for p in pieces:
                if p["used"] or NETTO_NAME_FONT not in p["font"]:
                    continue
                kind = None
                if re.fullmatch(r"[–-]\s?\d{1,2}\s?%", p["word"]):
                    kind = "discount"                     # any size: the big one-product pages print "-22%" very big
                elif re.fullmatch(r"(UVP |statt )\d{1,3}(\.\d{3})*\.(\d\d|[-–])?", p["word"]) and p["size"] <= 20:
                    kind = "old"                          # "UVP 0.99", "statt 1.19", "UVP 1.299." (+ a separate "–")
                elif re.fullmatch(r"\d{1,3}(\.\d{3})*\.(\d\d|[-–])", p["word"]) and p["size"] <= 20:
                    middle_y = (p["top"] + p["bottom"]) / 2
                    for line in strike_lines:            # a plain "1.69" is an old price only if it is CROSSED OUT
                        if line["left"] < p["right"] and line["right"] > p["left"] and abs(line["top"] - middle_y) <= 3:
                            kind = "old"                  # (a price table "Kinder Kuschelhoodie 7.99" is not crossed out)
                elif p["word"] in NETTO_LABELS and p["size"] <= 21:
                    kind = "label"
                elif re.fullmatch(r"\d+ für", p["word"]) and p["size"] <= 21:
                    kind = "multi"
                if kind is None:
                    continue
                nearest = None
                for price in prices:
                    if nearest is None or netto_distance(p, price) < netto_distance(p, nearest):
                        nearest = price
                if nearest is None or netto_distance(p, nearest) > 30:
                    continue
                p["used"] = True
                if kind == "discount" and nearest["discount"] is None:
                    nearest["discount"] = int(re.search(r"\d+", p["word"]).group())
                elif kind == "old" and nearest["old"] is None:
                    nearest["old"] = netto_money(p["word"].replace("UVP ", "").replace("statt ", ""))
                elif kind == "label":
                    nearest["labels"].append(p["word"])
                    if p["word"] == "+APP":
                        nearest["app"] = True
                elif kind == "multi":
                    nearest["multi"] = int(p["word"].split()[0])

            # 5. lines from the pieces that are left; each line gets a kind by its LOOK
            lines = {}
            for p in pieces:
                if not p["used"] and p["word"] not in ["*", "*1", "1", "ab", "je", "nur"]:    # marks at a price box
                    lines.setdefault((p["block"], p["line"]), []).append(p)
            line_list = []
            for line_pieces in lines.values():
                text = netto_clean(" ".join(" ".join(p["text"] for p in line_pieces).split()))
                main = max(line_pieces, key=lambda p: len(p["word"]))       # the piece with the most letters decides
                letters = sum(ch.isalpha() for ch in text)
                if NETTO_NAME_FONT in main["font"] and 8.5 <= main["size"] <= 15 and letters >= 1 and text not in NETTO_LABELS:
                    kind = "name"                             # ("3,6 V" has 1 letter: fine for the 2nd line of a name)
                elif NETTO_TEXT_FONT in main["font"] and 6.3 <= main["size"] <= 8.6:
                    kind = "description"
                else:
                    kind = "other"
                line_list.append({"text": text, "kind": kind, "used": False, "letters": letters,
                                  "left": min(p["left"] for p in line_pieces), "right": max(p["right"] for p in line_pieces),
                                  "top": min(p["top"] for p in line_pieces), "bottom": max(p["bottom"] for p in line_pieces)})
            line_list.sort(key=lambda line: (line["top"], line["left"]))

            # 6. products: a product STARTS at a name line and takes the lines directly below it
            #    (same left edge - bullet lines may start a little more to the right - and a small gap)
            products = []
            for start in line_list:
                if start["kind"] != "name" or start["used"] or start["letters"] < 2:
                    continue                                     # a name starts with a real word (at least 2 letters)
                group = [start]
                start["used"] = True
                last = start
                while True:
                    next_line = None
                    for line in line_list:
                        if line["used"] or line["kind"] == "other":
                            continue
                        if start["left"] - 3 <= line["left"] <= start["left"] + 8 and -2 <= line["top"] - last["bottom"] <= 4:
                            next_line = line
                            break
                    if next_line is None:
                        break
                    if next_line["kind"] == "name" and any(line["kind"] == "description" for line in group):
                        break                                    # a new name after the description = the NEXT product
                    next_line["used"] = True
                    group.append(next_line)
                    last = next_line
                names = [line["text"] for line in group if line["kind"] == "name"]
                descriptions = [line["text"] for line in group if line["kind"] == "description"]
                if not descriptions:
                    continue                                     # a name without description = a banner, not a product
                description = netto_join_lines(descriptions)
                # unit prices "(2.38 / kg)" and app unit prices "(App: 2.12 / kg)". There can be more than one:
                # "Einzelpreis: 1.69 (1.35 / l)  ab 2 Flaschen (1.03 / l)" -> all of them are kept for the check
                unit_prices, app_unit_prices = [], []
                for match in re.finditer(NETTO_UNIT_PRICE, description):
                    if match.group(1):
                        app_unit_prices.append(match.group())
                    else:
                        unit_prices.append(match.group())
                # weight = the LAST size written before the first unit price ("ohne Knochen, ca. 2,4 kg 1 kg" -> "1 kg")
                weight = ""
                if unit_prices:
                    before = description.split(unit_prices[0])[0]
                    found = re.findall(NETTO_SIZE, before)
                    if found:
                        weight = found[-1]
                if weight == "" and "•" not in description:      # no unit price: the description ENDS with the size
                                                                 # (not for "•" lists = non-food: "mit elastischem Bund")
                    end = description.split("Einzelpreis")[0].split("zzgl.")[0].strip(" ,")
                    match = re.search(r"(" + NETTO_SIZE + r"|Stück|Bund)(?: [A-Za-zäöüß]+){0,2}$", end)
                    if match:                                    # "1 kg offene Schale", "versch. Sorten, Stück", "Ägypten Bund"
                        weight = match.group(1)
                without_app = re.search(r"Preis ohne App: (" + NETTO_PRICE + ")", description)
                products.append({"name": netto_join_lines(names), "description": description, "weight": weight,
                                 "unit_price": " ".join(unit_prices), "app_unit_price": " ".join(app_unit_prices),
                                 "price_without_app": netto_money(without_app.group(1)) if without_app else None,
                                 "left": min(line["left"] for line in group), "right": max(line["right"] for line in group),
                                 "top": min(line["top"] for line in group), "bottom": max(line["bottom"] for line in group),
                                 "price": None, "app_price": None})

            # 7. pair products and price boxes. Each price is used once; a product gets at most one normal price
            #    and one app price. The best pairs are taken first:
            #    a) the price FITS the product's printed unit price (price / size = unit price) -> the flyer's own maths says yes
            #    b) otherwise by position: the price box sits where the product text ENDS (to the right, or below),
            #       so we measure from the bottom-right corner of the text, and skip boxes on the left side
            #    c) a price that does NOT fit a printed unit price is only the last choice
            pairs = []
            for i in range(len(products)):
                product = products[i]
                for j in range(len(prices)):
                    price = prices[j]
                    box_x, box_y = (price["left"] + price["right"]) / 2, (price["top"] + price["bottom"]) / 2
                    distance = ((box_x - product["right"]) ** 2 + (box_y - product["bottom"]) ** 2) ** 0.5
                    check_text = product["app_unit_price"] if price["app"] else product["unit_price"]
                    if check_text and netto_unit_price_fits(price["value"], product["weight"], check_text, price["multi"]):
                        cost = distance - 10000                       # a) confirmed by the unit price
                    elif box_x < product["left"] or distance > (600 if price["size"] >= 60 else 300):
                        continue                                      # b) box on the left side, or far away (a huge price
                                                                      #    on a one-product page may be far from the text)
                    elif check_text:
                        cost = distance + 10000                       # c) a unit price is printed, but it does not fit
                    else:
                        cost = distance
                    if price["app"] and not product["app_unit_price"] and product["price_without_app"] is None:
                        cost = cost + 10000                           # an app price for a product without app text: last choice
                    pairs.append((cost, i, j))
            pairs.sort()
            for cost, i, j in pairs:
                product, price = products[i], prices[j]
                if price["owner"] is not None:
                    continue
                slot = "app_price" if price["app"] else "price"
                if product[slot] is None:
                    product[slot] = price
                    price["owner"] = i

            # 7b. a product with an app price but no normal price: Netto prints the normal price box
            #     right NEXT to the app box (on its left side, same height) -> it belongs to the same product
            for i, product in enumerate(products):
                app_box = product["app_price"]
                if app_box is None or product["price"] is not None:
                    continue
                for price in prices:
                    if price["owner"] is None and not price["app"] and price["left"] < app_box["left"] \
                            and -15 <= app_box["left"] - price["right"] <= 20 \
                            and price["top"] < app_box["bottom"] and price["bottom"] > app_box["top"]:
                        product["price"] = price
                        price["owner"] = i
                        break

            # 8. one row per product, + one row per normal price box that no product took
            #    (verify.py may give such a price to a product whose unit price says it must be that price)
            page_rows = []
            for product in products:
                page_rows.append(netto_row(page, product, product["price"], product["app_price"], page_dates))
                print("Page", page, "-", product["name"], "->",
                      product["price"]["value"] if product["price"] else "NO PRICE",
                      "(app " + str(product["app_price"]["value"]) + ")" if product["app_price"] else "")
            unpaired_prices = []
            for price in prices:
                if price["owner"] is None:
                    unpaired_prices.append(netto_money_text(price["value"]))
                    if not price["app"]:
                        page_rows.append(netto_row(page, None, price, None, page_dates))
            all_offers = all_offers + page_rows
            page_summary.append({
                "page": page,
                "products": len(products),
                "prices": len(prices),
                "products_without_price": sum(1 for p in products if p["price"] is None and p["app_price"] is None),
                "unpaired_prices": " ".join(unpaired_prices),
                "error": "",
            })

        except Exception as error:
            page_summary.append({"page": page, "products": 0, "prices": 0, "products_without_price": 0,
                                 "unpaired_prices": "", "error": str(error)})
            print("ERROR on page", page, "->", error)

        page = page + 1

    # 9. dates: the flyer's main dates = the ones printed most often ("Montag 09.11. – Samstag 14.11.26").
    #    A page uses its own dates only if they lie inside the main dates (e.g. "Donnerstag 12.11. – Samstag 14.11.26");
    #    a page without such dates gets the main dates. (No dates at all -> validate.py uses the pipeline's week.)
    main_dates = max(flyer_dates, key=flyer_dates.count) if flyer_dates else (None, None)
    for offer in all_offers:
        start, end = main_dates
        for page_start, page_end in offer["page_dates"]:
            if main_dates[0] and main_dates[0] <= page_start <= page_end <= main_dates[1]:
                start, end = page_start, page_end
        offer["valid_from"] = start.isoformat() if start else ""
        offer["valid_to"] = end.isoformat() if end else ""
        del offer["page_dates"]

    # 10. save all offers in one file + the page summary (used by evaluate.py)
    if not any(offer["product_name"] for offer in all_offers):
        raise Exception("no Netto products found on any page - did Netto change the flyer design (fonts)?")
    with open(output_folder + "/offers.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=all_offers[0].keys())
        writer.writeheader()
        writer.writerows(all_offers)
    with open(output_folder + "/page_summary.csv", "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=page_summary[0].keys())
        writer.writeheader()
        writer.writerows(page_summary)
    products = sum(1 for offer in all_offers if offer["product_name"])
    print("Done!", products, "Netto products (+", len(all_offers) - products, "prices without a product) saved in",
          output_folder + "/offers.csv | main dates:", main_dates[0], "-", main_dates[1])


# =====================================================================================================
# RUN every store of config/settings.yaml with its own function (kaufland() and netto() above)
# (only when started as a program - python pipeline/structure.py - not when the tests read this file)
# =====================================================================================================
if __name__ == "__main__":
    STORE_PARTS = {"kaufland": kaufland, "netto": netto}
    for store in storage.stores():
        if store not in STORE_PARTS:
            print("\n" + store + ": structure.py has no function for this store yet - skipped")
            continue
        if not os.path.exists("data/text/" + store + "/page_1.csv"):
            print("\n" + store + ": no pages (no flyer, or an earlier stage failed) - skipped")
            continue
        print("\n----- " + store + " -----")
        try:
            STORE_PARTS[store]()
        except Exception as error:
            storage.store_failed(store, "structure", error)
# Lidl flyer -> offers CSV   (version 5 - same idea as Kaufland + Netto: read the flyer by how the text LOOKS)
#
# On a Lidl flyer:
#   brand        = CAPITAL bold words at the start of the name -> "DELUXE", "CHEF SELECT", "METZGERFRISCH"
#   product name = bold lines                                  -> "Italienische Wurstspezialität"
#   description  = normal (not bold) small lines under it      -> "Versch. Sorten. Gekühlt.", "Ursprung: Spanien"
#   weight       = the text after "Je" (or "Ca.")              -> "Je 100 g", "Je 80/100 g", "Je Topf", "Ca. 580 g"
#   unit price   = "1 kg = 19.90", "1 kg = 24.88/19.90", "1 WL = -.19", "kg-Preis = 7.99"
#   price        = BIG euros "1." + smaller cents "99", printed in YELLOW or RED -> 1.99  (stars "*", "d)" are skipped)
#   Lidl Plus    = the price right under "Mit Lidl Plus" (any colour); "Normalpreis: 2.49" = the price WITHOUT Lidl Plus
#   old price    = small grey "2.99" next to the "-33%" box, or "UVP 47.99"
#   dates        = BIG banners per SECTION: "Ab Mo. 16.11.", "Ab Do. 19.11." -> the nearest banner ABOVE the product
#                  in its column; the year comes from the footer "47/2026"
#
# NEW in version 5 (fewer "needs review"):
#   - online pages print the price FAR to the right of the text: a product without a price now takes a price
#     nobody took on its page (same row first) -> note "price far from the text (2nd round)"
#   - big prices that are NOT yellow/red (a dark blue Lidl Plus price) are kept as "spare" prices: used under
#     "Mit Lidl Plus" and for a product that finds no other price -> note "the price is not yellow/red"
#   - when the unit price CONFIRMS the offer price, an old price / discount that does not fit is removed
#     (it came from a neighbour) instead of sending the offer to review
#   - footnotes like "1)" after a price
#   - "price_candidates" starts with "page 5: 0 prices read for 4 products" (0 = the prices are pictures, not text)
# version 4: the price colour (yellow/red). version 3: soft hyphens, "12.5 g", "Normalpreis", Lidl Plus checks, ...
#
# Run (from the project folder):   python netto_try/lidl_offers.py
# Results:
#   data/output/offers_lidl.csv        -> the good offers (11 columns, no empty cells)
#   data/review/lidl/needs_review.csv  -> offers whose numbers do not fit (see "problems" and "price_candidates")
#   data/review/lidl/all_offers.csv    -> every offer with all details

import os
import csv
import re
import glob
import datetime
import pymupdf

STORE = "lidl"
BOLD_WORDS = ["Bold", "Black", "Heavy", "Semibold", "SemiBold", "Demi", "ExtraBold", "Extrabold"]
NOT_BRANDS = ["BIO", "XXL", "NEU", "NEW", "MSC", "ASC"]   # capital words that are not a brand
LABELS = ["Aktion", "Nur online", "Auch online", "Tiefpreis", "Probierpreis", "Super Sonntag"]
PER_LABELS = {"kg-Preis": "1 kg", "100-g-Preis": "100 g", "l-Preis": "1 l"}    # turned text next to a price
PRICE_COLOURS = ["yellow", "red"]                         # Lidl prints its prices in these colours
FOOTNOTE = r"\*{0,2} ?[a-z0-9]{0,2}\)|\*{1,2}|[¹²³⁴⁵⁶⁷⁸⁹⁰]{1,2}"     # a piece that is only "*", "tt)", "*d)", "1)"
STAR = r"\s?\*{0,2}\s?(?:[a-z0-9]{1,2}\)|[¹²³⁴⁵⁶⁷⁸⁹⁰]{1,2})?"        # "*", "* tt)", "*d)", "*1)" at the end of a price
PREFIX = r"(?:(?:ab|nur|je|Ab|Nur|Je)\s)?"                # "nur 4.99", "ab 9.99"
WEEKDAY = r"(?:Mo|Di|Mi|Do|Fr|Sa|So)\."
WHOLE_PRICE = PREFIX + r"(\d{1,4}|[-–])\.(\d\d)" + STAR                # a price in one piece: "1.99", "-.99", "nur 4.99*"
EURO_PIECE = PREFIX + r"(\d{1,3}(?:\.\d{3})*|[-–])\.?([-–]?)" + STAR   # only the euros: "1." (+ cents "99"), "249.-"

# a size: "100 g", "2x100 g", "12x 12.5 g", "1,75 l", "80 WL"
NUMBER = r"\d+(?:,\d+|\.\d{1,2}(?!\d))?"                  # "100", "1,5", "12.5"  (but not "1.050")
UNIT = r"(?:kg|g|ml|cl|l|Liter|Stück|St\.|m|Meter|WL|Blatt|Rollen)(?![A-Za-zäöüß])"
AMOUNT = r"(?:\d+\s?x\s?)?" + NUMBER + r"\s?" + UNIT
SIZE = r"(?:" + NUMBER + r"\s?[–-]\s?)?" + AMOUNT + r"(?:\s?[–-]\s?" + AMOUNT + r")?"
# a unit price: "1 kg = 19.90", "1 kg = 24.88/19.90", "1 WL = -.19/-.21"   and   "kg-Preis = 7.99"
PRICE_VALUE = r"(?:\d+|[-–])\.\d\d"
UNIT_PRICE = r"(\d+(?:,\d+)?)\s?(kg|g|l|ml|m|WL)\s?=\s?(" + PRICE_VALUE + r"(?:\s?/\s?" + PRICE_VALUE + r")*)"
KG_PRICE = r"\b(kg|l|100-g)-Preis\s?=?\s?(\d+\.\d\d)"
# where the weight text after "Je" ends
WEIGHT_STOP = r";| zzgl\.| Abtropf| Normalpreis| Standardpackung| Entspricht| \d+(?:,\d+)? ?(?:kg|g|l|ml|m|WL) ?=|\. "

pdf_files = sorted(glob.glob("data/flyers/lidl/lidl_*.pdf"))
if not pdf_files:
    print("No Lidl flyer found in data/flyers/lidl")
    exit(1)
pdf_path = pdf_files[-1]                                   # the newest flyer, e.g. lidl_2026-W47.pdf
os.makedirs("data/output", exist_ok=True)
os.makedirs("data/review/lidl", exist_ok=True)


def clean(text):
    """thin spaces -> normal spaces (the invisible soft hyphen is handled in make_lines)"""
    return text.replace("\u2009", " ").replace("\u202f", " ").replace("\xa0", " ")


def gap(a, b):
    """distance between two boxes (0 if they touch or overlap)"""
    dx = max(0, a["left"] - b["right"], b["left"] - a["right"])
    dy = max(0, a["top"] - b["bottom"], b["top"] - a["bottom"])
    return (dx ** 2 + dy ** 2) ** 0.5


def price_value(text):
    """'19.90' -> 19.9 ,  '-.19' -> 0.19"""
    text = text.strip().replace("–", "-")
    if text.startswith("-."):
        text = "0" + text[1:]
    return float(text)


def colour_name(color):
    """the colour of a text piece: 'yellow', 'red', or its code like '#ffffff' (white) or '#1a1a1a' (black)"""
    if not isinstance(color, int):
        return "unknown"
    r, g, b = (color >> 16) & 255, (color >> 8) & 255, color & 255
    if r >= 200 and g >= 160 and b <= 120:
        return "yellow"                                    # Lidl yellow, about #fff000
    if r >= 160 and g <= 100 and b <= 120:
        return "red"                                       # Lidl red, about #e60a14
    return "#%02x%02x%02x" % (r, g, b)


def join_lines(lines):
    """join lines into one text:
    a soft hyphen at the line end joins the word ('Weih' + 'nachtsmann' -> 'Weihnachtsmann', 'METZ' + 'GER' + 'FRISCH');
    a normal hyphen before a small letter too ('Wurst-' + 'spezialität' -> 'Wurstspezialität')"""
    result = ""
    for line in lines:
        line = line.strip()
        if line == "":
            continue
        if result.endswith("\xad"):
            result = result[:-1] + line
        elif result.endswith("-") and line[:1].islower() and line.split()[0] not in ["und", "oder"]:
            result = result[:-1] + line
        elif result.endswith("-") or result == "":
            result = result + line
        else:
            result = result + " " + line
    return " ".join(result.replace("\xad", "").split())


def sizes_of(text):
    """every '100 g', '2x100 g', '12x 12.5 g', '1,75 l', '80 WL' in a text -> [(0.1, 'kg'), (0.2, 'kg'), ...]"""
    result = []
    for count, amount, unit in re.findall(r"(?:(\d+)\s?x\s?)?(" + NUMBER + r")\s?(" + UNIT + r")", text):
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


def all_sizes(text):
    """EVERY size written in a description (the unit prices themselves are left out):
    'Je 80/100 g' -> 80 g and 100 g ,  'Je 1 kg; Abtropfgewicht: 900 g' -> 1 kg and 900 g ,  'Ca. 580 g' -> 580 g"""
    text = re.sub(UNIT_PRICE, " ", text)
    text = re.sub(KG_PRICE, " ", text)
    result = []
    for numbers, unit in re.findall(r"(\d+(?:,\d+)?(?:\s?/\s?\d+(?:,\d+)?)+)\s?(kg|g|ml|cl|l|WL)(?![A-Za-zäöüß])", text):
        for number in numbers.split("/"):
            result = result + sizes_of(number.strip() + " " + unit)     # "80/100 g": both numbers get the unit
    return result + sizes_of(text)


def unit_prices_of(text):
    """'1 kg = 19.90' -> [(1, 'kg', 19.9)] ,  '1 kg = 24.88/19.90' -> two ,  '1 WL = -.19' -> [(1, 'WL', 0.19)] ,
    'kg-Preis = 7.99' -> [(1, 'kg', 7.99)]"""
    result = []
    for amount, unit, values in re.findall(UNIT_PRICE, text):
        base = float(amount.replace(",", "."))
        base_unit = unit
        if unit == "g":
            base, base_unit = base / 1000, "kg"
        elif unit == "ml":
            base, base_unit = base / 1000, "l"
        for value in values.split("/"):
            result.append((base, base_unit, price_value(value)))
    for kind, value in re.findall(KG_PRICE, text):
        if kind == "100-g":
            result.append((0.1, "kg", float(value)))
        else:
            result.append((1.0, kind, float(value)))
    return result


def fits(price, sizes, unit_prices):
    """True if price / size = a printed unit price, for ANY size and ANY unit price (1% or 1 cent for rounding)"""
    if price is None:
        return False
    for base, base_unit, unit_price in unit_prices:
        for size, size_unit in sizes:
            if size_unit == base_unit and size > 0:
                if abs(price / size * base - unit_price) <= max(unit_price * 0.01, 0.01):
                    return True
    return False


def weight_text(description):
    """the weight as written: 'Je 80/100 g; 1 kg = ...' -> '80/100 g' ,  'Je Topf' -> 'Topf' ,
    'Je ca. Ø 2 x H 30 cm. Je Set' -> 'Set' ,  'JeSet' -> 'Set' ,  'Ca. 580 g' -> 'ca. 580 g' ,  'kg-Preis' -> '1 kg'"""
    candidates = []
    for match in re.finditer(r"\bJe\s*(?=[A-ZÄÖÜ0-9])", description):
        candidates.append(re.split(WEIGHT_STOP, description[match.end():])[0].strip(" .,"))
    for weight in candidates:
        if re.match(SIZE, weight):
            return weight                                  # a "Je" with a size wins ("Je 100 g")
    if candidates:
        return candidates[-1]                              # otherwise the last one ("Je Stück", "Je Set")
    ca = re.search(r"\b[Cc]a\. ?(" + AMOUNT + ")", description)
    if ca:
        return "ca. " + ca.group(1)
    if re.search(r"\bkg-Preis\b", description):
        return "1 kg"                                      # "Klasse I; kg-Preis" = the price is per kg
    return ""


def make_lines(pieces):
    """pieces of the same PDF line -> one line with its text, its biggest piece ("main") and its box.
    A soft hyphen at the end of a line is kept as a mark (join_lines then joins the word with the next line)."""
    groups = {}
    for p in pieces:
        groups.setdefault((p["block"], p["line"]), []).append(p)
    lines = []
    for line_pieces in groups.values():
        raw = clean(" ".join(p["text"] for p in line_pieces))
        soft = raw.rstrip().endswith("\xad")
        text = " ".join(raw.replace("\xad", "").split())
        if soft:
            text = text + "\xad"
        main = max(line_pieces, key=lambda p: len(p["word"]))
        lines.append({"text": text, "pieces": line_pieces, "main": main, "used": False,
                      "left": min(p["left"] for p in line_pieces), "right": max(p["right"] for p in line_pieces),
                      "top": min(p["top"] for p in line_pieces), "bottom": max(p["bottom"] for p in line_pieces)})
    return lines


def read_price(p, pieces):
    """a price that STARTS at piece p -> (value, right edge, cents piece or None), or None if p is not a price.
    '1.99' in one piece, or the euros '1.' + the smaller cents '99' right next to it (top half), or '249.-'.
    With the colour rule ON the cents must have the same colour as the euros."""
    match = re.fullmatch(WHOLE_PRICE, p["word"])
    if match:
        euros = "0" if match.group(1) in ["-", "–"] else match.group(1)
        return float(euros + "." + match.group(2)), p["right"], None
    match = re.fullmatch(EURO_PIECE, p["word"])
    if match is None:
        return None
    euros = "0" if match.group(1) in ["-", "–"] else match.group(1).replace(".", "")
    if match.group(2):
        return float(euros + ".00"), p["right"], None     # "249.-" = 249.00
    for c in pieces:
        if c is p or c["used"] or c["size"] > p["size"]:
            continue
        if COLOUR_RULE and c["colour"] != p["colour"]:
            continue                                       # the cents have the SAME colour as the euros
        if p["right"] - p["size"] * 0.4 <= c["left"] <= p["right"] + p["size"] * 0.35 \
                and p["top"] - p["size"] * 0.2 <= c["top"] <= (p["top"] + p["bottom"]) / 2:
            cents_match = re.fullmatch(r"\.?(\d\d)" + STAR, c["word"])
            if cents_match:
                return float(euros + "." + cents_match.group(1)), max(p["right"], c["right"]), c
            if re.fullmatch(r"[-–]+" + STAR, c["word"]):
                return float(euros + ".00"), max(p["right"], c["right"]), c
    return None


# 1. read every page: every piece of text WITH its look (size, bold, COLOUR), and the coloured bands
pdf = pymupdf.open(pdf_path)
pages = []
for page in pdf:
    pieces = []
    for block in page.get_text("dict")["blocks"]:
        for line_number, line in enumerate(block.get("lines", [])):
            horizontal = abs(line["dir"][1]) < 0.3                # False = turned text like "kg-Preis"
            for span in line["spans"]:
                if span["text"].strip() == "":
                    continue
                left, top, right, bottom = span["bbox"]
                bold = (span["flags"] & 16) != 0 or any(word in span["font"] for word in BOLD_WORDS)
                pieces.append({"text": span["text"], "word": clean(span["text"]).replace("\xad", "").strip(),
                               "left": left, "top": top, "right": right, "bottom": bottom,
                               "font": span["font"], "size": span["size"], "bold": bold, "horizontal": horizontal,
                               "colour": colour_name(span["color"]),
                               "block": block["number"], "line": line_number, "used": False})
    bands = []
    for drawing in page.get_drawings():
        r = drawing["rect"]
        if drawing.get("fill") and r.width >= 30 and r.height >= 8:
            bands.append({"left": r.x0, "top": r.y0, "right": r.x1, "bottom": r.y1})
    pages.append({"number": page.number + 1, "pieces": pieces, "bands": bands, "width": page.rect.width})

# 2. MEASURE the description size D: the most common size of "Je ..." and "1 kg = ..." lines
sizes = []
for page in pages:
    for line in make_lines(page["pieces"]):
        if re.match(r"Je \S", line["text"]) or re.search(UNIT_PRICE, line["text"]):
            sizes.append(round(line["main"]["size"], 1))
if not sizes:
    print("No 'Je ...' or '1 kg = ...' lines found - does this flyer have real text? (see explore_lidl.py)")
    exit(1)
D = max(set(sizes), key=sizes.count)          # D = the description size; everything else is compared with it
PRICE_MIN = 1.8 * D                           # the big euros of a price are at least this size
COLOUR_PRICE_MIN = 1.3 * D                    # a YELLOW/RED price may be smaller (colour rule ON)

# 2b. CHECK the price colours: every big number shaped like a price ("1.99", "1.") is counted once per spot
#     (a price printed twice - colour + outline - counts once). Most spots yellow/red -> the colour rule is ON.
spots_total, spots_coloured = 0, 0
for page in pages:
    spots = []
    for p in page["pieces"]:
        if not p["horizontal"] or p["size"] < PRICE_MIN:
            continue
        if not (re.fullmatch(WHOLE_PRICE, p["word"]) or re.fullmatch(PREFIX + r"\d{1,3}\." + STAR, p["word"])):
            continue
        coloured = p["colour"] in PRICE_COLOURS
        same = None
        for spot in spots:
            if abs(spot["left"] - p["left"]) < p["size"] * 0.3 and abs(spot["top"] - p["top"]) < p["size"] * 0.3:
                same = spot
                break
        if same is None:
            spots.append({"left": p["left"], "top": p["top"], "coloured": coloured})
        elif coloured:
            same["coloured"] = True
    spots_total = spots_total + len(spots)
    spots_coloured = spots_coloured + sum(1 for spot in spots if spot["coloured"])
COLOUR_RULE = spots_total >= 10 and spots_coloured >= 0.6 * spots_total

# 3. the week and year from the footer "HHZ – 47/2026 – DE" / "AUSGABE 47/2026"
editions = []
for page in pages:
    for line in make_lines(page["pieces"]):
        for week_text, year_text in re.findall(r"\b(\d{1,2})/(20\d\d)\b", line["text"]):
            if 1 <= int(week_text) <= 53:
                editions.append((int(year_text), int(week_text)))
if editions:
    year, week_number = max(set(editions), key=editions.count)
else:                                                      # no footer: take the week from the file name
    found = re.search(r"(\d{4})-W(\d\d)", pdf_path)
    year, week_number = int(found.group(1)), int(found.group(2))
week = str(year) + "-W" + str(week_number).zfill(2)
monday = datetime.date.fromisocalendar(year, week_number, 1)


def to_date(day, month):
    """'16.11.' -> 2026-11-16  (the year from the footer; a date far from the flyer week belongs to the next/last year)"""
    try:
        date = datetime.date(year, month, day)
        if (date - monday).days > 180:
            date = date.replace(year=year - 1)
        elif (monday - date).days > 180:
            date = date.replace(year=year + 1)
        return date
    except ValueError:
        return None


def continues_above(line, lines):
    """True if the line just above ends with '/' or '=' ('1 kg = 3.45/2.79/' + '2.60'):
    then this number belongs to that unit price - it is NOT an old price"""
    for other in lines:
        if other is line:
            continue
        above = -0.3 * D <= line["top"] - other["bottom"] <= 0.9 * D and abs(other["left"] - line["left"]) <= 3 * D
        if above and other["text"].rstrip("\xad ").endswith(("/", "=")):
            return True
    return False


all_rows = []
all_banners = []
bold_fonts = []
price_colours = {}
spare_total = 0
pages_without_prices = []

for page in pages:
    pieces = page["pieces"]
    page_lines = make_lines(pieces)

    # 4. date banners: BIG text "Ab Mo. 16.11. bis Sa. 21.11." / "Ab Do. 19.11." (small date text inside a
    #    description is NOT a banner). The coloured band behind the banner shows the column the dates belong to.
    banners = []
    for line in page_lines:
        if line["main"]["size"] < 1.4 * D:
            continue
        match = re.search(r"\bAb " + WEEKDAY + r" ?(\d{1,2})\.(\d{1,2})\.(?: ?bis " + WEEKDAY + r" ?(\d{1,2})\.(\d{1,2})\.)?",
                          line["text"])
        if match is None:
            continue
        start = to_date(int(match.group(1)), int(match.group(2)))
        end = to_date(int(match.group(3)), int(match.group(4))) if match.group(3) else None
        if start is None:
            continue
        x, y = (line["left"] + line["right"]) / 2, (line["top"] + line["bottom"]) / 2
        band = None
        for b in page["bands"]:
            if b["left"] <= x <= b["right"] and b["top"] <= y <= b["bottom"] and b["right"] - b["left"] >= line["right"] - line["left"]:
                if band is None or (b["right"] - b["left"]) * (b["bottom"] - b["top"]) < (band["right"] - band["left"]) * (band["bottom"] - band["top"]):
                    band = b                                   # the smallest band around the banner text
        if band is not None:
            left, right = band["left"], band["right"]
        else:
            left, right = line["left"] - page["width"] / 6, line["right"] + page["width"] / 6
        banners.append({"start": start, "end": end, "left": left, "right": right, "bottom": line["bottom"]})
        all_banners.append((start, end))
        for p in line["pieces"]:
            p["used"] = True                                   # a banner is not product text

    # 5. prices. colour rule ON : 1st pass = YELLOW/RED prices (at least COLOUR_PRICE_MIN) -> the real prices
    #                              2nd pass = BIG prices in another colour (at least PRICE_MIN) -> "spare" prices,
    #                                         used only under "Mit Lidl Plus" or when a product finds no other price
    #            colour rule OFF: BIG prices (at least PRICE_MIN), any colour
    prices = []
    spare_prices = []
    for first_pass in [True, False]:
        if not first_pass and not COLOUR_RULE:
            break
        for p in pieces:
            if p["used"] or not p["horizontal"]:
                continue
            if first_pass and COLOUR_RULE:
                if p["colour"] not in PRICE_COLOURS or p["size"] < COLOUR_PRICE_MIN:
                    continue
            elif p["size"] < PRICE_MIN:
                continue
            found = read_price(p, pieces)
            if found is None:
                continue
            value, right, cents_piece = found
            p["used"] = True
            if cents_piece is not None:
                cents_piece["used"] = True
            duplicate = any(abs(q["left"] - p["left"]) < p["size"] * 0.3 and abs(q["top"] - p["top"]) < p["size"] * 0.3
                            for q in prices + spare_prices)
            if duplicate:
                continue                                   # the same price printed twice (outline + colour)
            new_price = {"value": value, "app": False, "left": p["left"], "top": p["top"], "right": right,
                         "bottom": p["bottom"], "old": None, "discount": None, "per": "",
                         "weight_box": "", "owner": None, "colour": p["colour"]}
            if first_pass:
                prices.append(new_price)
                price_colours[p["colour"]] = price_colours.get(p["colour"], 0) + 1
            else:
                spare_prices.append(new_price)
                spare_total = spare_total + 1

    # 6. Lidl Plus: the price right UNDER the text "Mit Lidl Plus" is the Lidl Plus price (any colour)
    for line in page_lines:
        if "Mit Lidl Plus" not in line["text"]:
            continue
        best = None
        for price in prices + spare_prices:
            below = -D <= price["top"] - line["bottom"] <= 10 * D
            near = price["left"] < line["right"] + 3 * D and price["right"] > line["left"] - 3 * D
            if below and near and (best is None or price["top"] < best["top"]):
                best = price
        if best is not None:
            best["app"] = True
            if not any(price is best for price in prices):     # a spare price (e.g. dark blue) -> a real price now
                spare_prices = [price for price in spare_prices if price is not best]
                prices.append(best)
        for p in line["pieces"]:
            p["used"] = True

    # 7. small things: "-33%", old price "2.99" / "UVP 47.99", "kg-Preis", the weight box "1,5 kg", labels
    rest = [p for p in pieces if not p["used"] and not re.fullmatch(FOOTNOTE, p["word"])]
    label_lines = []
    for line in make_lines(rest):
        text = line["text"].rstrip("\xad")
        if any(text.startswith(label) for label in LABELS):
            label_lines.append(line)                       # labels go to the nearest PRODUCT (after step 9)
            continue
        kind, discount, old, per, weight_box = None, None, None, "", ""
        rest_text = text
        found = re.search(r"[-–]\s?(\d{1,2})\s?%", rest_text)
        if found:
            discount = int(found.group(1))
            rest_text = rest_text.replace(found.group(), " ")
        found = re.search(r"(?:UVP\s?)?(\d{1,4}\.\d\d)", rest_text)
        if found and line["main"]["size"] < PRICE_MIN and not (discount is None and continues_above(line, page_lines)):
            old = float(found.group(1))
            rest_text = rest_text.replace(found.group(), " ")
        if rest_text.strip() in ["", "UVP"] and (discount is not None or old is not None):
            kind = "price info"                            # the line holds ONLY a discount and/or an old price
        elif text in PER_LABELS:
            kind, per = "per", PER_LABELS[text]
        elif re.fullmatch(SIZE, text) and line["main"]["bold"]:
            kind, weight_box = "weight box", text          # "1,5 kg" in the box over the price
        if kind is None:
            continue
        nearest = None
        for price in prices:
            if nearest is None or gap(line, price) < gap(line, nearest):
                nearest = price
        if nearest is None or gap(line, nearest) > 8 * D:
            continue
        for p in line["pieces"]:
            p["used"] = True
        if discount is not None and nearest["discount"] is None:
            nearest["discount"] = discount
        if old is not None and nearest["old"] is None:
            nearest["old"] = old
        if per:
            nearest["per"] = per
        if weight_box:
            nearest["weight_box"] = weight_box
    for line in label_lines:
        for p in line["pieces"]:
            p["used"] = True

    # 8. lines that are left -> name lines (bold) and description lines (not bold)
    product_lines = make_lines([p for p in pieces if not p["used"] and p["horizontal"]
                                and not re.fullmatch(FOOTNOTE, p["word"])])
    for line in product_lines:
        main = line["main"]
        letters = sum(ch.isalpha() for ch in line["text"])
        line["letters"] = letters
        if re.match(r"Je \S", line["text"]) or re.search(UNIT_PRICE, line["text"]) or re.search(KG_PRICE, line["text"]):
            line["kind"] = "description"                   # weight and unit price lines are always description
        elif main["bold"] and 0.9 * D <= main["size"] <= 2.6 * D and letters >= 1:
            line["kind"] = "name"
        elif not main["bold"] and 0.75 * D <= main["size"] <= 1.4 * D:
            line["kind"] = "description"
        else:
            line["kind"] = "other"
    product_lines.sort(key=lambda line: (line["top"], line["left"]))

    # 9. products: a product STARTS at a name line and takes the lines directly below it (same left edge)
    products = []
    for start in product_lines:
        if start["kind"] != "name" or start["used"] or start["letters"] < 2:
            continue
        group = [start]
        start["used"] = True
        last = start
        while True:
            next_line = None
            for line in product_lines:
                if line["used"] or line["kind"] == "other":
                    continue
                if start["left"] - 0.5 * D <= line["left"] <= start["left"] + 1.5 * D \
                        and -0.4 * D <= line["top"] - last["bottom"] <= 0.9 * D:
                    next_line = line
                    break
            if next_line is None:
                break
            if next_line["kind"] == "name" and any(line["kind"] == "description" for line in group):
                break                                      # a new name after the description = the NEXT product
            next_line["used"] = True
            group.append(next_line)
            last = next_line
        names = [line["text"] for line in group if line["kind"] == "name"]
        descriptions = [line["text"] for line in group if line["kind"] == "description"]
        if not descriptions:
            continue                                       # a name without description = a headline, not a product
        name = join_lines(names)
        if name.endswith(("!", "?")):
            continue                                       # "Entdecke weitere ... auf lidl-fotos.de!" = a headline
        if group[0]["main"]["font"] not in bold_fonts:
            bold_fonts.append(group[0]["main"]["font"])

        # brand = the CAPITAL words at the start of the name ("CHEF SELECT Kartoffelgratin ...")
        words = name.split()
        brand_words = []
        for word in words:
            letters_only = re.sub(r"[^A-Za-zÄÖÜäöüß]", "", word)
            if len(letters_only) >= 2 and letters_only.isupper() and letters_only not in NOT_BRANDS:
                brand_words.append(word)
            else:
                break
        if brand_words and len(brand_words) < len(words):
            brand = " ".join(brand_words)
            name = " ".join(words[len(brand_words):])
        else:
            brand = ""

        description = join_lines(descriptions)
        products.append({"name": name, "brand": brand, "description": description,
                         "weight": weight_text(description), "labels": [], "extra_notes": [],
                         "left": min(l["left"] for l in group), "right": max(l["right"] for l in group),
                         "top": min(l["top"] for l in group), "bottom": max(l["bottom"] for l in group),
                         "price": None, "app_price": None, "price_candidates": ""})

    # 9b. a small "product" without "Je", weight or unit price directly UNDER a real product is part of it
    #     ("Standardgröße ca. 135 x 200 cm" under the bed linen - it must not take the bed linen's price)
    products.sort(key=lambda product: product["top"])
    kept = []
    for product in products:
        parent = None
        if not re.search(r"\bJe\s*[A-ZÄÖÜ0-9]", product["description"]) and product["weight"] == "" \
                and not re.search(UNIT_PRICE, product["description"]):
            for other in kept:
                if abs(other["left"] - product["left"]) <= 1.5 * D and -0.5 * D <= product["top"] - other["bottom"] <= 3 * D:
                    parent = other
        if parent is None:
            kept.append(product)
        else:
            parent["description"] = join_lines([parent["description"], product["brand"], product["name"], product["description"]])
            parent["bottom"] = max(parent["bottom"], product["bottom"])
            parent["right"] = max(parent["right"], product["right"])
    products = kept
    for product in products:                               # sizes and unit prices from the (maybe longer) description
        product["sizes"] = all_sizes(product["description"])
        product["unit_prices"] = unit_prices_of(product["description"])
        product["unit_price"] = " ".join([m.group() for m in re.finditer(UNIT_PRICE, product["description"])]
                                         + [m.group() for m in re.finditer(KG_PRICE, product["description"])])

    # labels ("Aktion", "Nur online", ...) go to the nearest product
    for line in label_lines:
        nearest = None
        for product in products:
            if nearest is None or gap(line, product) < gap(line, nearest):
                nearest = product
        if nearest is not None and gap(line, nearest) <= 12 * D and line["text"].rstrip("\xad") not in nearest["labels"]:
            nearest["labels"].append(line["text"].rstrip("\xad"))

    # 10a. pair products and prices. Each price is used once; a product gets one normal and one Lidl Plus price.
    #      - the price FITS the printed unit price -> first (also a Lidl Plus price: Lidl often prints its unit price)
    #      - by position: near the bottom-right corner of the text; price bottom = last text line bottom (bonus);
    #        a price on the LEFT is possible (fruit tiles), but ranked lower; a BIG price may stand further away
    #      - a normal price that does NOT fit a printed unit price -> last choice
    pairs = []
    for i in range(len(products)):
        product = products[i]
        for j in range(len(prices)):
            price = prices[j]
            box_x, box_y = (price["left"] + price["right"]) / 2, (price["top"] + price["bottom"]) / 2
            distance = ((box_x - product["right"]) ** 2 + (box_y - product["bottom"]) ** 2) ** 0.5
            if distance > max(45 * D, 8 * (price["bottom"] - price["top"])):
                continue                                   # far away
            cost = distance
            if box_x < product["left"]:
                cost = cost + 15 * D                       # on the left side: possible, but less likely
            if abs(price["bottom"] - product["bottom"]) <= 1.5 * D:
                cost = cost - 10 * D                       # the price stands on the same line as the last text line
            if product["unit_prices"]:
                if fits(price["value"], product["sizes"], product["unit_prices"]):
                    cost = cost - 100000                   # confirmed by the unit price
                elif not price["app"]:
                    cost = cost + 100000                   # a unit price is printed, but it does not fit
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

    # 10b. 2nd round: a product still WITHOUT a price takes a price NOBODY took on this page, also far away
    #      (online pages print the price far on the right, in the same row as the text).
    #      A price in the same ROW comes first, then other leftover prices up to 80 D away. Nearest first.
    #      If the product has a unit price, the price must fit it.
    second = []
    for i, product in enumerate(products):
        if product["price"] is not None or product["app_price"] is not None:
            continue
        for j, price in enumerate(prices):
            if price["owner"] is not None:
                continue
            if product["unit_prices"] and not fits(price["value"], product["sizes"], product["unit_prices"]):
                continue
            box_x, box_y = (price["left"] + price["right"]) / 2, (price["top"] + price["bottom"]) / 2
            distance = ((box_x - product["right"]) ** 2 + (box_y - product["bottom"]) ** 2) ** 0.5
            same_row = price["bottom"] >= product["top"] - 6 * D and price["top"] <= product["bottom"] + 6 * D
            if same_row:
                second.append((distance, i, j))
            elif distance <= 80 * D:
                second.append((distance + 100 * D, i, j))
    second.sort()
    for cost, i, j in second:
        product, price = products[i], prices[j]
        if price["owner"] is not None or product["price"] is not None or product["app_price"] is not None:
            continue
        product["app_price" if price["app"] else "price"] = price
        price["owner"] = i
        product["extra_notes"].append("price far from the text (2nd round)")

    # 10c. still no price: a big SPARE price that is not yellow/red (e.g. dark blue) close to the product
    third = []
    for i, product in enumerate(products):
        if product["price"] is not None or product["app_price"] is not None:
            continue
        for j, price in enumerate(spare_prices):
            if price["owner"] is not None:
                continue
            if product["unit_prices"] and not fits(price["value"], product["sizes"], product["unit_prices"]):
                continue
            box_x, box_y = (price["left"] + price["right"]) / 2, (price["top"] + price["bottom"]) / 2
            distance = ((box_x - product["right"]) ** 2 + (box_y - product["bottom"]) ** 2) ** 0.5
            if distance <= max(45 * D, 8 * (price["bottom"] - price["top"])):
                third.append((distance, i, j))
    third.sort()
    for cost, i, j in third:
        product, price = products[i], spare_prices[j]
        if price["owner"] is not None or product["price"] is not None or product["app_price"] is not None:
            continue
        product["price"] = price
        price["owner"] = i
        prices.append(price)
        product["extra_notes"].append("the price is not yellow/red (" + price["colour"] + ")")

    # 10d. a Lidl Plus price but no normal price: the normal price stands right ABOVE the "Mit Lidl Plus" price
    for i, product in enumerate(products):
        app_box = product["app_price"]
        if app_box is None or product["price"] is not None:
            continue
        for price in prices:
            if price["owner"] is None and not price["app"] and price["bottom"] <= app_box["top"] + D \
                    and app_box["top"] - price["bottom"] <= 12 * D \
                    and price["left"] < app_box["right"] + 3 * D and price["right"] > app_box["left"] - 5 * D:
                product["price"] = price
                price["owner"] = i
                break

    # 10e. a Lidl Plus price is always LOWER than the normal price - a higher one came from a neighbour: remove it
    for product in products:
        if product["price"] is not None and product["app_price"] is not None \
                and product["app_price"]["value"] >= product["price"]["value"]:
            product["app_price"]["owner"] = None
            product["app_price"] = None
            product["extra_notes"].append("a Lidl Plus price higher than the normal price was removed")

    # no "Je ..." weight: take the weight box over the price ("1,5 kg") or "kg-Preis" (= 1 kg)
    for product in products:
        box = product["price"] or product["app_price"]
        if box is not None and box["weight_box"]:
            product["sizes"] = product["sizes"] + sizes_of(box["weight_box"])
            if product["weight"] == "":
                product["weight"] = box["weight_box"]
        if product["weight"] == "" and box is not None and box["per"]:
            product["weight"] = box["per"]
        # no price at all: write down what is near the product (to find out WHY - send this column to Claude)
        if box is None:
            near = ["page " + str(page["number"]) + ": " + str(len(prices)) + " prices read for "
                    + str(len(products)) + " products"]
            for p in pieces:
                if not p["used"] and p["size"] >= 1.2 * D and re.search(r"\d", p["word"]) and gap(p, product) <= 40 * D:
                    near.append("'" + p["word"] + "' size " + str(round(p["size"], 1)) + " " + p["colour"])
            for price in prices:
                if price["owner"] is not None and gap(price, product) <= 40 * D:
                    near.append(f"{price['value']:.2f} taken by {products[price['owner']]['name'][:30]}")
            for price in spare_prices:
                if price["owner"] is None and gap(price, product) <= 40 * D:
                    near.append(f"{price['value']:.2f} in {price['colour']} not taken")
            product["price_candidates"] = "; ".join(near[:12])
            if len(prices) == 0 and page["number"] not in pages_without_prices:
                pages_without_prices.append(page["number"])
        all_rows.append({"page": page["number"], "product": product, "banners": banners, "page_prices": prices})

# 11. dates: the main dates = the "bis" banner printed most often; without banners: Monday - Saturday of the week
with_end = [pair for pair in all_banners if pair[1] is not None]
if with_end:
    main_dates = max(set(with_end), key=with_end.count)
else:
    main_dates = (monday, monday + datetime.timedelta(days=5))


def dates_for(product, banners):
    """the nearest date banner ABOVE the product in its column; no banner -> the main dates"""
    best = None
    for banner in banners:
        if banner["bottom"] <= product["top"] + 2 and banner["left"] < product["right"] and banner["right"] > product["left"]:
            if best is None or banner["bottom"] > best["bottom"]:
                best = banner
    if best is None:
        return main_dates
    end = best["end"] or main_dates[1]                    # "Ab Do. 19.11." -> until the end of the flyer week
    if end < best["start"]:
        end = best["start"]
    return best["start"], end


def row_check(product):
    """-> (offer price, old price, discount, problems, notes)
    With "Normalpreis: 2.49" Lidl prints the Lidl Plus price big: then the offer price is the Normalpreis
    (the price everybody pays) and the big price goes into the description as the Lidl Plus price.
    When the unit price CONFIRMS the offer price, an old price / discount that does not fit came from a neighbour:
    it is removed (written in the notes) instead of sending the offer to review."""
    normal = product["price"]["value"] if product["price"] else None
    app = product["app_price"]["value"] if product["app_price"] else None
    box = product["price"] or product["app_price"]
    old = box["old"] if box else None
    discount = box["discount"] if box else None
    problems, notes = [], list(product["extra_notes"])
    if normal is None and app is not None and "Normalpreis" in product["description"]:
        found = re.search(r"Normalpreis:?\s?(\d+\.\d\d)", product["description"])
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
    if product["unit_prices"] and offer is not None:
        if fits(offer, product["sizes"], product["unit_prices"]):
            notes.append("unit price fits")
            confirmed = True
        elif app is not None and fits(app, product["sizes"], product["unit_prices"]):
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
                removed = removed + " and -" + str(discount) + "%"
            notes.append(removed + " removed: " + wrong + " (the offer price fits the unit price)")
            old, discount = None, None
        elif wrong:
            problems.append(wrong)
    return offer, old, discount, problems, notes


# 12. repair: the unit price tells us what the price MUST be -> look for that price on the same page
for row in all_rows:
    product = row["product"]
    offer, old, discount, problems, notes = row_check(product)
    if "price and unit price do not match" not in problems and "no price" not in problems:
        continue
    if not product["unit_prices"]:
        continue
    for price in row["page_prices"]:
        if price["app"] or price is product["price"]:
            continue
        owner = None
        for other in all_rows:
            if other["page"] == row["page"] and other["product"]["price"] is price:
                owner = other
        if owner is not None:
            owner_offer, owner_old, owner_discount, owner_problems, owner_notes = row_check(owner["product"])
            if not owner_problems:
                continue                                   # the owner's own price fits: never take it
        if fits(price["value"], product["sizes"], product["unit_prices"]):
            old_price = product["price"]
            product["price"] = price
            if owner is not None:
                owner["product"]["price"] = old_price       # swap
            product["repaired"] = True
            break

# 13. the final rows: brand from the capital words, name as printed, everything else in "description"
details = []
seen = []
for row in all_rows:
    product = row["product"]
    offer, old, discount, problems, notes = row_check(product)
    if product.get("repaired"):
        notes.append("price taken from a neighbour (confirmed by unit price)")
    start, end = dates_for(product, row["banners"])
    box = product["price"] or product["app_price"] or {"old": None, "discount": None, "per": "", "weight_box": "", "colour": ""}
    app_box = product["app_price"]
    app_price = app_box["value"] if app_box else None
    if offer is None and product["weight"] == "" and not product["unit_prices"]:
        status = "not an offer"
    elif any(word in " ".join(problems) for word in ["no price", "not match", "not higher"]):
        status = "check"
    else:
        status = "ok"
    applied = old is not None or discount is not None or app_price is not None or "Aktion" in product["labels"]
    key = (product["brand"], product["name"], product["weight"], offer, start, end)
    if key in seen:
        continue                                           # the same offer again
    seen.append(key)

    # the description: EVERYTHING the flyer says about this product, in one text
    parts = []
    if product["description"]:
        parts.append(product["description"])
    if old is not None:
        parts.append("old price: " + f"{old:.2f}")
    if discount is not None:
        parts.append("discount: -" + str(discount) + "%")
    if app_box is not None:
        parts.append("Lidl Plus price: " + f"{app_price:.2f}")
        if app_box is not box and app_box["discount"] is not None:
            parts.append("Lidl Plus discount: -" + str(app_box["discount"]) + "%")
    if box["per"]:
        parts.append("price per " + box["per"])
    if box["weight_box"]:
        parts.append("pack: " + box["weight_box"])
    if product["labels"]:
        parts.append("labels: " + ", ".join(product["labels"]))
    parts.append("page: " + str(row["page"]))

    details.append({
        "week": week, "store": STORE, "page": row["page"],
        "offer_start_date": start.isoformat(), "offer_end_date": end.isoformat(),
        "brand": product["brand"] or "UNKNOWN", "product_name": product["name"], "product_weight": product["weight"],
        "price_eur": f"{offer:.2f}" if offer is not None else "",
        "offer_applied": "yes" if applied else "no",
        "app_or_card_price": "yes" if app_price is not None else "no",
        "description": " | ".join(parts),
        "lidl_plus_price_eur": f"{app_price:.2f}" if app_price is not None else "",
        "old_price_eur": f"{old:.2f}" if old is not None else "",
        "discount_pct": discount if discount is not None else "",
        "unit_price": product["unit_price"],
        "price_colour": box["colour"],
        "status": status, "problems": "; ".join(problems), "notes": "; ".join(notes),
        "price_candidates": product["price_candidates"],
    })

# 14. save the files
if len(details) == 0:
    print("No products found - send data/explore/lidl_explore.txt to Claude")
    exit(1)
SIMPLE_COLUMNS = ["week", "store", "offer_start_date", "offer_end_date", "brand", "product_name",
                  "product_weight", "price_eur", "offer_applied", "app_or_card_price", "description"]
good = [d for d in details if d["status"] == "ok"]
for d in good:
    for column in SIMPLE_COLUMNS:
        if str(d[column]).strip() == "":
            d[column] = "UNKNOWN"                          # no empty cells (e.g. no size on a non-food product)
with open("data/output/offers_lidl.csv", "w", newline="", encoding="utf-8-sig") as file:
    writer = csv.DictWriter(file, fieldnames=SIMPLE_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(good)
with open("data/review/lidl/needs_review.csv", "w", newline="", encoding="utf-8-sig") as file:
    writer = csv.DictWriter(file, fieldnames=details[0].keys())
    writer.writeheader()
    writer.writerows([d for d in details if d["status"] == "check"])
with open("data/review/lidl/all_offers.csv", "w", newline="", encoding="utf-8-sig") as file:
    writer = csv.DictWriter(file, fieldnames=details[0].keys())
    writer.writeheader()
    writer.writerows(details)

checked = sum(1 for d in good if "unit price fits" in d["notes"])
with_brand = sum(1 for d in good if d["brand"] != "UNKNOWN")
second_round = sum(1 for d in good if "2nd round" in d["notes"])
spare_used = sum(1 for d in good if "not yellow/red" in d["notes"])
old_removed = sum(1 for d in good if " removed: " in d["notes"])
reasons = {}
for d in details:
    if d["status"] == "check":
        for problem in d["problems"].split("; "):
            reasons[problem] = reasons.get(problem, 0) + 1
print("Flyer:", pdf_path, "| pages:", len(pages), "| week:", week, "| main dates:", main_dates[0], "-", main_dates[1])
print("Measured description size:", D, "| price at least:", round(PRICE_MIN, 1), "| name fonts seen:", bold_fonts[:5])
print("Price colour check:", spots_coloured, "of", spots_total, "big price numbers are yellow/red -> colour rule",
      "ON (yellow/red prices from size " + str(round(COLOUR_PRICE_MIN, 1)) + ")" if COLOUR_RULE else "OFF (size rule only)")
print("Prices read:", sum(price_colours.values()), "| by colour:", price_colours, "| spare (other colour):", spare_total)
print("Products found:", len(all_rows), "| after removing repeats:", len(details))
print("  ok:", len(good), "(" + str(checked) + " confirmed by the unit price,", with_brand, "with a brand)")
print("     extra help: price far from the text:", second_round, "| price not yellow/red:", spare_used,
      "| wrong old price/discount removed:", old_removed)
print("  needs review:", sum(1 for d in details if d["status"] == "check"), "-> data/review/lidl/needs_review.csv")
print("     why:", reasons)
if pages_without_prices:
    print("     pages with products but NO price as text:", pages_without_prices,
          "(the prices there are probably pictures)")
print("  not an offer:", sum(1 for d in details if d["status"] == "not an offer"))
print("Done! data/output/offers_lidl.csv (11 columns: the 10 Kaufland columns + description)")
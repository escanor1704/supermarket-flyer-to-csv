# ALDI Nord flyer -> offers CSV
#
# How it works:
#   The ALDI PDF is made of PAGE PICTURES (632 x 1105 pixels) - there is no text inside, so PyMuPDF finds no words.
#   The pictures are read by how they LOOK (colours and shapes) plus OCR with RapidOCR (free, runs on this PC,
#   PaddleOCR's text models; the newest model reads German and finds the text lines itself, also white text on dark tiles):
#   1. price boxes = solid RED boxes with WHITE digits. Tall digits = euros, small digits at the top = cents ("1.19**")
#      -> euros and cents are read SEPARATELY (reading "1.19**" as one line gives "119" or "1.19**" - unclear)
#   2. the YELLOW labels on top of a box: "-33 %", "AKTION", "750 g"; the light strip under it: "UVP 2.59" / "1.79"
#      (crossed out); a red "kg-Preis" strip under it = the price is per kg
#   3. the whole page is read once (every text line with its place and height)
#   4. the product = the text block LEFT of the box (or above it): BRAND in small capitals, the NAME big,
#      the description small, ending with the unit price "(kg = 5.95)"
#   5. maths check: price / weight = unit price, old price - discount = price. One misread digit (1/7, 3/8, 5/6, ...)
#      is corrected when exactly one change makes the maths fit
#   6. dates from the banners "Mo. 9.11. – Sa. 14.11." / "ab Do. 12.11." (the nearest one above the box)
#
# Try and tune:
#   - first try a few pages:   python netto_try/aldi_offers.py 1-5        (all pages: python netto_try/aldi_offers.py)
#   - look at data/review/aldi/pages/page_N.png: blue = price box + the price read, orange = label/old price, green = text
#   - the page reading is saved in data/text/aldi/<flyer>/ -> the next run is faster (delete it to read again)
#   - the first run downloads the OCR models once (internet needed one time)
#
# Needs (all free, pip only):   pip install "rapidocr==3.10.0" onnxruntime

import os
import re
import csv
import sys
import glob
import datetime
import numpy
import cv2
import pymupdf
from rapidocr import RapidOCR

STORE = "aldi"
OCR_WIDTH = 1600                  # a page picture is made this wide before the page is read (bigger = better small text, slower)
MIN_SCORE = 0.5                   # text lines the OCR is less sure about (0-1) are dropped
LABEL_LINES = ["IM AUFSTELLER", "AKTION", "KURZE WEGE", "MEHR FRISCHE", "unverpackt", "Verschiedene Modelle",
               "Weitere Duftrichtungen", "Dessinvarianten", "Dessin-varianten"]
NOT_BRANDS = ["XXL", "BIO", "NEU", "UVP"]
CONFUSED = {"0": "68", "1": "74", "2": "7", "3": "85", "4": "19", "5": "63", "6": "580", "7": "12", "8": "3609",
            "9": "84"}            # digits OCR mixes up
WEEKDAY = r"(?:Mo|Di|Mi|Do|Fr|Sa|So)"
DATE = WEEKDAY + r"\.?\s?(\d{1,2})\.\s?(\d{1,2})\.?"
UNIT = r"(?:kg|g|ml|cl|l|L|Liter)(?![A-Za-zäöüß])"
SIZE = r"(?:\d+\s?[x×]\s?)?\d+(?:[.,]\d+)?\s?-?\s?" + UNIT                 # "200-g", "1-L", "5 kg", "2 x 100 g"
UNIT_PRICE = r"(1\s?kg|kg|1\s?l|Liter|l|100\s?g|100\s?ml|1\s?m|m|Stück)\s?=\s?(\d+[.,]\d\d(?:\s?/\s?\d+[.,]\d\d)*)"
PRODUCT_WORDS = r"\b(?:Stück|Packung|Beutel|Glas|Netz|Set|Lose Ware|Garnitur|Paar|Flasche|Dose|Becher|Schale)\b"

# RapidOCR: pip only. The settings are tried first; if this rapidocr does not know them -> default settings
try:
    engine = RapidOCR(params={"Global.log_level": "warning", "Global.max_side_len": 3000})
except Exception:
    engine = RapidOCR()
engine(numpy.full((64, 256, 3), 255, numpy.uint8))         # loads the OCR models now (the first time: downloads them)

pdf_files = sorted(glob.glob("data/flyers/aldi/aldi_*.pdf"))
if not pdf_files:
    print("No ALDI flyer found in data/flyers/aldi")
    exit(1)
pdf_path = pdf_files[-1]                                   # the newest flyer, e.g. aldi_2026-W46.pdf
found = re.search(r"(\d{4})-W(\d\d)", pdf_path)
if found is None:
    print("The file name needs the week, e.g. aldi_2026-W46.pdf")
    exit(1)
year, week_number = int(found.group(1)), int(found.group(2))
week = str(year) + "-W" + str(week_number).zfill(2)
monday = datetime.date.fromisocalendar(year, week_number, 1)
flyer_name = os.path.splitext(os.path.basename(pdf_path))[0]
cache_folder = "data/text/aldi/" + flyer_name
picture_folder = "data/review/aldi/pages"
for folder in ["data/output", "data/review/aldi", picture_folder, cache_folder]:
    os.makedirs(folder, exist_ok=True)


def clean(text):
    """OCR junk out: '|Finesse_' -> 'Finesse'"""
    text = re.sub(r"[^\wÄÖÜäöüß .,;:\-–/()%&+'=*Ø]", " ", str(text))
    return " ".join(text.replace("_", " ").split())


def overlap(a, b):
    """how much two boxes cover each other: 0 = not at all, 1 = the smaller one lies completely inside the bigger one"""
    width = min(a["right"], b["right"]) - max(a["left"], b["left"])
    height = min(a["bottom"], b["bottom"]) - max(a["top"], b["top"])
    if width <= 0 or height <= 0:
        return 0
    smaller = min((a["right"] - a["left"]) * (a["bottom"] - a["top"]), (b["right"] - b["left"]) * (b["bottom"] - b["top"]))
    return width * height / max(smaller, 1)


def page_picture(pdf, page):
    """the biggest picture of the page as an OpenCV picture (blue-green-red), in its full size.
    No picture on the page -> the page is drawn at 300 dpi."""
    best = None
    for info in page.get_images(full=True):
        if best is None or info[2] * info[3] > best[2] * best[3]:
            best = info
    if best is not None:
        pix = pymupdf.Pixmap(pdf, best[0])
    else:
        pix = page.get_pixmap(dpi=300)
    if pix.n - pix.alpha >= 4 or pix.n - pix.alpha == 1:   # CMYK or grey -> RGB
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    if pix.alpha:
        pix = pymupdf.Pixmap(pix, 0)                       # no transparency
    rgb = numpy.frombuffer(pix.samples, dtype=numpy.uint8).reshape(pix.height, pix.width, pix.n)
    return cv2.cvtColor(numpy.ascontiguousarray(rgb[:, :, :3]), cv2.COLOR_RGB2BGR)


def colour_masks(picture):
    """where the picture is ALDI red or label yellow, plus the grey picture (the brightness: white digits are bright -
    the brightness is stored sharper than the colour in a JPG picture, so the digits are cut out of the grey picture)"""
    hsv = cv2.cvtColor(picture, cv2.COLOR_BGR2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    red = (((h <= 8) | (h >= 170)) & (s >= 150) & (v >= 110)).astype(numpy.uint8) * 255
    yellow = ((h >= 18) & (h <= 35) & (s >= 120) & (v >= 170)).astype(numpy.uint8) * 255
    return red, yellow, cv2.cvtColor(picture, cv2.COLOR_BGR2GRAY)


def solid_boxes(mask, U):
    """solid coloured rectangles in a colour mask -> [{left, top, right, bottom}] (photos are not solid -> skipped)"""
    size = max(1, round(3 * U))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, numpy.ones((size, size), numpy.uint8))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w >= 12 * U and h >= 8 * U and cv2.contourArea(contour) >= 0.80 * w * h:
            boxes.append({"left": x, "top": y, "right": x + w, "bottom": y + h})
    return boxes


def recognise(picture):
    """read ONE line of text in a small picture (the line is given, no search) -> (text, score 0-1)"""
    if picture is None or picture.shape[0] < 3 or picture.shape[1] < 3:
        return "", 0.0
    if picture.ndim == 2:
        picture = cv2.cvtColor(picture, cv2.COLOR_GRAY2BGR)
    result = engine(numpy.ascontiguousarray(picture), use_det=False, use_cls=False, use_rec=True)
    texts = getattr(result, "txts", None)
    if texts is None or len(texts) == 0:
        return "", 0.0
    first = texts[0]
    if isinstance(first, (tuple, list)):                   # some versions give (text, score) pairs
        return str(first[0]), float(first[1])
    scores = getattr(result, "scores", None)
    return str(first), (float(scores[0]) if scores is not None and len(scores) > 0 else 0.0)


def ocr_line(picture, make_binary=True, remove_lines=False):
    """read ONE line of text in a small picture -> text.
    make_binary: black text on a white background first (for the price digits and the old price)"""
    if picture is None or picture.shape[0] < 3 or picture.shape[1] < 3:
        return ""
    if make_binary:
        grey = picture if picture.ndim == 2 else cv2.cvtColor(picture, cv2.COLOR_BGR2GRAY)
        scale = max(1.0, 64 / grey.shape[0])
        big = cv2.resize(grey, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        _, picture = cv2.threshold(big, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        if numpy.mean(picture) < 127:
            picture = 255 - picture                        # dark background -> white background with black text
        if remove_lines:                                   # the line that crosses out an old price
            ink = 255 - picture
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, picture.shape[1] // 3), 1))
            ink = cv2.subtract(ink, cv2.morphologyEx(ink, cv2.MORPH_OPEN, kernel))
            picture = 255 - ink
        picture = cv2.copyMakeBorder(picture, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
    return clean(recognise(picture)[0])


def read_digits(labels, blobs):
    """the digits of some white shapes in a price box -> '119' (first all together, then shape by shape)"""
    if not blobs:
        return ""
    top, bottom = min(b["top"] for b in blobs), max(b["bottom"] for b in blobs)
    left, right = min(b["left"] for b in blobs), max(b["right"] for b in blobs)
    part = numpy.isin(labels[top:bottom, left:right], [b["number"] for b in blobs])
    together = re.sub(r"\D", "", ocr_line(numpy.where(part, 0, 255).astype(numpy.uint8)))
    if len(together) == len(blobs):
        return together
    one_by_one = ""
    for blob in sorted(blobs, key=lambda b: b["left"]):
        part = labels[blob["top"]:blob["bottom"], blob["left"]:blob["right"]] == blob["number"]
        digit = re.sub(r"\D", "", ocr_line(numpy.where(part, 0, 255).astype(numpy.uint8)))[:1]
        if digit == "" and blob["width"] < 0.4 * blob["height"]:
            digit = "1"                                    # a thin shape is a "1"
        one_by_one = one_by_one + (digit or "?")
    return one_by_one if "?" not in one_by_one else together


def read_price_box(grey, box, U):
    """the price in a red box: tall white digits = euros, the smaller ones at the top right = cents
    -> {"price", "euros", "sure", "raw"} or None (no big white digits = not a price box)"""
    margin = max(1, round(2 * U))
    top, bottom = box["top"] + margin, box["bottom"] - margin
    left, right = box["left"] + margin, box["right"] - margin
    if bottom - top < 10 or right - left < 10:
        return None
    _, digits = cv2.threshold(numpy.ascontiguousarray(grey[top:bottom, left:right]), 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    if numpy.mean(digits) > 127:
        return None                                        # mostly bright: not white digits on a red box
    count, labels, stats, _ = cv2.connectedComponentsWithStats(digits, connectivity=8)
    blobs = []
    for number in range(1, count):
        x, y, w, h, size = [int(value) for value in stats[number]]
        if size >= 5 * U * U and (h >= 0.12 * (bottom - top) or w >= 0.15 * (bottom - top)):     # digits or a dash "–"
            blobs.append({"number": number, "left": x, "top": y, "right": x + w, "bottom": y + h, "width": w, "height": h})
    if not blobs:
        return None
    tallest = max(b["height"] for b in blobs)
    if tallest < 0.40 * (bottom - top):
        return None                                        # no big digits: a red box with words, not a price
    euros = sorted([b for b in blobs if b["height"] >= 0.75 * tallest], key=lambda b: b["left"])
    if len(euros) > 4:
        return None                                        # too many big shapes: words, not a price
    euro_right = max(b["right"] for b in euros)
    euro_top = min(b["top"] for b in euros)
    small = [b for b in blobs if 0.25 * tallest <= b["height"] < 0.75 * tallest
             and b["left"] >= euro_right - 0.15 * tallest and b["top"] <= euro_top + 0.35 * tallest]
    cents = []
    if small:                                              # the cents are the BIGGER small shapes (the stars are smaller)
        cents_height = max(b["height"] for b in small)
        cents = sorted([b for b in small if b["height"] >= 0.75 * cents_height], key=lambda b: b["left"])[:2]
    dash = [b for b in blobs if all(b is not e for e in euros) and b["width"] >= 2 * b["height"]
            and b["left"] >= euro_right - 0.15 * tallest and b["top"] <= euro_top + 0.6 * tallest]
    euro_text = read_digits(labels, euros)
    cents_text = "00" if (dash and not cents) else read_digits(labels, cents)
    raw = "euros '" + euro_text + "' (" + str(len(euros)) + " shapes), cents '" + cents_text + "' (" + str(len(cents)) + " shapes)"
    if euro_text == "" or len(euro_text) > 4:
        return {"price": None, "euros": None, "sure": False, "raw": raw}
    if len(cents_text) != 2:
        return {"price": None, "euros": int(euro_text), "sure": False, "raw": raw}
    sure = len(euro_text) == len(euros) and (len(cents) == 2 or bool(dash))
    return {"price": int(euro_text) + int(cents_text) / 100, "euros": int(euro_text), "sure": sure, "raw": raw}


def labels_above(box, yellow_boxes, picture, U):
    """the yellow boxes stacked on top of a price box: "-33 %", "AKTION", "750 g" / "XXL 5 kg" """
    result = {"discount": None, "labels": [], "weight_box": "", "areas": []}
    current = box["top"]
    for step in range(3):
        best = None
        for yellow in yellow_boxes:
            if any(yellow is area for area in result["areas"]):
                continue
            width = min(yellow["right"], box["right"]) - max(yellow["left"], box["left"])
            if width >= 0.4 * min(yellow["right"] - yellow["left"], box["right"] - box["left"]) \
                    and -8 * U <= current - yellow["bottom"] <= 14 * U:
                if best is None or yellow["bottom"] > best["bottom"]:
                    best = yellow
        if best is None:
            break
        current = best["top"]
        result["areas"].append(best)
        text = ocr_line(picture[best["top"]:best["bottom"], best["left"]:best["right"]], make_binary=False)
        discount = re.search(r"(\d{1,2})\s?%", text)
        size = re.search(r"\d+(?:[.,]\d+)?\s?(?:kg|g|ml|l)\b", text)
        if discount and result["discount"] is None:
            result["discount"] = int(discount.group(1))
        elif size and not result["weight_box"]:
            result["weight_box"] = size.group()
            if "XXL" in text.upper():
                result["labels"].append("XXL")
        elif "AKT" in text.upper():
            result["labels"].append("AKTION")
        elif len(text) >= 2:
            result["labels"].append(text)
    return result


def old_price_below(box, picture, U):
    """the light strip under a price box: 'UVP 2.59' or a crossed-out '1.79' -> (old price or None, strip area or None)"""
    height = box["bottom"] - box["top"]
    top, bottom = box["bottom"], min(picture.shape[0], box["bottom"] + int(0.45 * height))
    if bottom - top < 6 * U:
        return None, None
    crop = picture[top:bottom, box["left"]:box["right"]]
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    if numpy.median(hsv[:, :, 2]) < 150 or numpy.median(hsv[:, :, 1]) > 110:
        return None, None                                  # not a light strip
    area = {"left": box["left"], "top": top, "right": box["right"], "bottom": bottom}
    text = ocr_line(crop, remove_lines=True)
    found = re.search(r"(\d{1,4})[.,](\d\d)", text)
    if found is None:
        return None, area
    return int(found.group(1)) + int(found.group(2)) / 100, area


def per_strip(box, strips, picture, U):
    """a red strip "kg-Preis" under the price box -> ("1 kg" or "100 g", strip) or ("", None)"""
    height = box["bottom"] - box["top"]
    for strip in strips:
        width = min(strip["right"], box["right"]) - max(strip["left"], box["left"])
        if width >= 0.5 * (strip["right"] - strip["left"]) and box["bottom"] - 2 * U <= strip["top"] <= box["bottom"] + 0.9 * height:
            text = ocr_line(picture[strip["top"]:strip["bottom"], strip["left"]:strip["right"]], make_binary=False)
            if "reis" in text or "kg" in text:
                return ("100 g" if "100" in text else "1 kg"), strip
    return "", None


def page_lines(picture, cache_file):
    """every text line on the page with its place (in picture pixels), its height and how sure the OCR is.
    RapidOCR finds the lines itself (black text on light tiles and white text on dark tiles).
    Saved, so the next run does not read the page again."""
    if os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8-sig") as file:
            lines = [{"text": row["text"], "conf": float(row["conf"]), "left": float(row["left"]), "top": float(row["top"]),
                      "right": float(row["right"]), "bottom": float(row["bottom"])} for row in csv.DictReader(file)]
    else:
        scale = OCR_WIDTH / picture.shape[1]
        big = cv2.resize(picture, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        result = engine(big, use_cls=False)
        boxes = getattr(result, "boxes", None)
        texts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        lines = []
        if boxes is not None and texts is not None:
            if scores is None:
                scores = [1.0] * len(texts)
            for points, text, score in zip(boxes, texts, scores):
                if isinstance(text, (tuple, list)):        # some versions give (text, score) pairs
                    text, score = text[0], text[1]
                text = clean(text)
                if float(score) < MIN_SCORE or not re.search(r"[A-Za-zÄÖÜäöüß0-9]", text):
                    continue
                xs = [float(point[0]) for point in points]
                ys = [float(point[1]) for point in points]
                lines.append({"text": text, "conf": round(float(score) * 100), "left": min(xs) / scale,
                              "top": min(ys) / scale, "right": max(xs) / scale, "bottom": max(ys) / scale})
        with open(cache_file, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.DictWriter(file, fieldnames=["text", "conf", "left", "top", "right", "bottom"])
            writer.writeheader()
            writer.writerows(lines)
    for line in lines:
        line["height"] = line["bottom"] - line["top"]
    return lines


def to_date(day, month):
    """'9.11.' -> 2026-11-09 (the year from the file name); a date far away from the flyer week -> None"""
    for year_try in [year, year + 1, year - 1]:
        try:
            date = datetime.date(year_try, month, day)
        except ValueError:
            return None
        if -7 <= (date - monday).days <= 20:
            return date
    return None


def date_lines(lines):
    """lines with a date: 'Mo. 9.11. – Sa. 14.11.' (start + end) or 'ab Do. 12.11.' (start only)"""
    result = []
    for line in lines:
        dates = re.findall(DATE, line["text"])
        if not dates:
            continue
        start = to_date(int(dates[0][0]), int(dates[0][1]))
        end = to_date(int(dates[-1][0]), int(dates[-1][1])) if len(dates) >= 2 else None
        if start is None:
            continue
        if end is not None and end < start:
            end = None
        result.append({"start": start, "end": end, "left": line["left"], "right": line["right"],
                       "top": line["top"], "bottom": line["bottom"]})
    return result


def sizes_of(text):
    """every size in a text: '200-g-Packung' -> (0.2, 'kg'), '1-L-Packung' -> (1, 'l'), '4er-Packung' -> (4, 'Stück')"""
    text = re.sub(UNIT_PRICE, " ", text)
    result = []
    for count, amount, unit in re.findall(r"(?:(\d+)\s?[x×]\s?)?(\d+(?:[.,]\d+)?)\s?-?\s?(kg|g|ml|cl|l|L|Liter)(?![A-Za-zäöüß])", text):
        total = float(amount.replace(",", ".")) * (int(count) if count else 1)
        unit = unit.lower()
        if unit == "g":
            result.append((total / 1000, "kg"))
        elif unit == "ml":
            result.append((total / 1000, "l"))
        elif unit == "cl":
            result.append((total / 100, "l"))
        elif unit in ["l", "liter"]:
            result.append((total, "l"))
        else:
            result.append((total, "kg"))
    for count in re.findall(r"(\d+)\s?(?:-?Stück|er-)", text):
        result.append((float(count), "Stück"))
    return result


def unit_prices_of(text):
    """'(kg = 13.90)' -> [(1, 'kg', 13.9)], '(kg = 12.90/8.60)' -> two, '(Liter = 0.88)' -> [(1, 'l', 0.88)]"""
    result = []
    for base_text, values in re.findall(UNIT_PRICE, text):
        base_text = base_text.replace(" ", "")
        if base_text in ["kg", "1kg"]:
            base, base_unit = 1.0, "kg"
        elif base_text == "100g":
            base, base_unit = 0.1, "kg"
        elif base_text in ["l", "1l", "Liter"]:
            base, base_unit = 1.0, "l"
        elif base_text == "100ml":
            base, base_unit = 0.1, "l"
        elif base_text in ["m", "1m"]:
            base, base_unit = 1.0, "m"
        else:
            base, base_unit = 1.0, "Stück"
        for value in values.split("/"):
            result.append((base, base_unit, float(value.strip().replace(",", "."))))
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


def discount_fits(price, old, discount):
    """True if old price - discount % = price (1 point for rounding)"""
    if price is None or old is None or discount is None or old <= 0:
        return False
    percent = (1 - price / old) * 100
    return min(abs(int(percent) - discount), abs(round(percent) - discount)) <= 1


def weight_text(text):
    """the weight as written: '200-g-Packung' -> '200 g', '100 g bzw. 150 g' -> '100 g bzw. 150 g', 'Stück' -> 'Stück'"""
    text = re.sub(UNIT_PRICE, " ", text)
    found = []
    for match in re.finditer(SIZE, text):
        size = " ".join(re.sub(r"\s?-\s?", " ", match.group()).replace("Liter", "l").replace("L", "l").split())
        if size not in found:
            found.append(size)
    if len(found) >= 2 and "bzw" in text:
        return " bzw. ".join(found[:3])
    if found:
        return found[0]
    pack = re.search(r"\d+er-Packung", text)
    if pack:
        return pack.group()
    for word in ["Stück", "Set", "Garnitur", "Paar"]:
        if re.search(r"\b" + word + r"\b", text):
            return word
    return ""


def join_text(texts):
    """lines -> one text; a word split at the line end is joined ('Rinder-' + 'gulasch' -> 'Rindergulasch')"""
    result = ""
    for text in texts:
        text = text.strip()
        if text == "":
            continue
        if result.endswith("-") and text[:1].islower():
            result = result[:-1] + text
        elif result.endswith("-") or result == "":
            result = result + text
        else:
            result = result + " " + text
    return result


def mostly_caps(text):
    """True for 'HERTA', 'HOME CREATION', 'DR. QUENDT' (small capitals = the brand line)"""
    letters = [ch for ch in text if ch.isalpha()]
    return len(letters) >= 2 and sum(ch.isupper() for ch in letters) >= 0.75 * len(letters)


def columns_of(lines, U):
    """lines with the same left edge, one under the other -> text blocks"""
    columns = []
    for line in sorted(lines, key=lambda l: l["top"]):
        for column in columns:
            if abs(line["left"] - column["left"]) <= 10 * U:
                column["lines"].append(line)
                break
        else:
            columns.append({"left": line["left"], "lines": [line]})
    blocks = []
    for column in columns:
        run = []
        for line in column["lines"]:
            if run and line["top"] - run[-1]["bottom"] > 1.5 * min(line["height"], run[-1]["height"]) + 4 * U:
                blocks.append(run)
                run = []
            run.append(line)
        if run:
            blocks.append(run)
    return blocks


def blocks_near(box, lines, boxes, U):
    """possible text blocks of a price box: the lines LEFT of the box (usual) or ABOVE it (big tiles)"""
    width, height = box["right"] - box["left"], box["bottom"] - box["top"]
    left_limit = box["left"] - 3.5 * width
    top_limit = box["top"] - 2.8 * height
    for other in boxes:
        if other is box:
            continue
        same_row = other["bottom"] > box["top"] - height and other["top"] < box["bottom"] + height
        if same_row and other["right"] <= box["left"]:
            left_limit = max(left_limit, other["right"])           # the text never goes past the next box on the left
        same_column = other["right"] > box["left"] - width and other["left"] < box["right"] + width
        if same_column and other["bottom"] <= box["top"]:
            top_limit = max(top_limit, other["bottom"])
    left_lines = [l for l in lines if l["right"] <= box["left"] + 0.25 * width and l["left"] >= left_limit - 5 * U
                  and l["top"] >= box["top"] - 1.6 * height and l["bottom"] <= box["bottom"] + 0.8 * height]
    above_lines = [l for l in lines if l["bottom"] <= box["top"] + 0.25 * height and l["top"] >= top_limit
                   and box["left"] - 0.7 * width <= l["left"] <= box["right"] and l["right"] <= box["right"] + 1.6 * width]
    return [("left", block) for block in columns_of(left_lines, U)] + [("above", block) for block in columns_of(above_lines, U)]


def block_score(layout, block, box):
    """how much a text block looks like the product text of this box (None = not product text at all)"""
    text = join_text([l["text"] for l in block])
    if sum(ch.isalpha() for ch in text) < 3:
        return None
    width, height = box["right"] - box["left"], box["bottom"] - box["top"]
    score = 0.0
    if re.search(UNIT_PRICE, text):
        score = score + 5                                  # "(kg = 5.95)"
    if re.search(SIZE, text) or re.search(PRODUCT_WORDS, text):
        score = score + 3                                  # "200-g-Packung", "Stück"
    heights = [l["height"] for l in block]
    if max(heights) >= 1.45 * min(heights):
        score = score + 2                                  # a big name line
    if mostly_caps(block[0]["text"]):
        score = score + 1                                  # the brand line on top
    score = score + 0.3 * min(len(block), 6)
    right, bottom = max(l["right"] for l in block), max(l["bottom"] for l in block)
    if layout == "left":
        score = score - max(0, box["left"] - right) / width - abs(bottom - box["bottom"]) / height
    else:
        score = score - max(0, box["top"] - bottom) / height - 0.5
    return score


def split_block(block):
    """a text block -> (labels, brand, name, description).  brand = small capitals on top, name = the big lines"""
    labels, lines = [], []
    for line in block:
        if len(line["text"]) <= 25 and any(label.lower() in line["text"].lower() for label in LABEL_LINES):
            labels.append(clean(line["text"]))
        else:
            lines.append(line)
    if not lines:
        return labels, "", "", ""
    smallest = min(l["height"] for l in lines)
    big = [i for i, l in enumerate(lines) if l["height"] >= 1.45 * smallest]
    if big:
        first, last = big[0], big[-1]
    else:
        first = 1 if len(lines) > 1 and mostly_caps(lines[0]["text"]) else 0
        last = first
    brand_lines = [l["text"] for l in lines[:first] if mostly_caps(l["text"])]
    other_before = [l["text"] for l in lines[:first] if not mostly_caps(l["text"])]       # e.g. "3+" (age)
    brand = clean(join_text(brand_lines)).strip(" .,;:-")
    if brand.upper() in NOT_BRANDS:
        brand = ""
    name = clean(join_text([l["text"] for l in lines[first:last + 1]])).strip(" .,;:")
    description = clean(join_text(other_before + [l["text"] for l in lines[last + 1:]]))
    return labels, brand, name, description


def price_variants(value):
    """the price with ONE digit changed the way OCR mixes digits up: 1.79 -> 1.19, 7.79, 1.29, ..."""
    text = str(int(round(value * 100)))
    result = []
    for i, digit in enumerate(text):
        for other in CONFUSED.get(digit, ""):
            new = int(text[:i] + other + text[i + 1:])
            if new > 0:
                result.append(new / 100)
    return result


def confirmations(price, old, discount, sizes, unit_prices):
    reasons = []
    if unit_prices and fits(price, sizes, unit_prices):
        reasons.append("unit price fits")
    if discount_fits(price, old, discount):
        reasons.append("old price and discount fit")
    return reasons


def check_row(product):
    """the maths checks (and repairs) -> (price, old price, discount, problems, notes)"""
    price, old, discount = product["price"], product["old"], product["discount"]
    sizes, unit_prices = product["sizes"], product["unit_prices"]
    problems, notes = [], []
    if not sizes and unit_prices:
        sizes = [(1.0, "kg"), (1.0, "l"), (1.0, "Stück")]  # no size written ("Lose Ware"): the price may be per kg
    if price is None and product["euros"] is not None and unit_prices:
        for base, base_unit, unit_price in unit_prices:   # euros read, cents not: the unit price tells the cents
            for size, size_unit in sizes:
                if size_unit == base_unit and base > 0:
                    expected = round(unit_price * size / base, 2)
                    if int(expected) == product["euros"]:
                        price = expected
        if price is not None:
            notes.append("cents from the unit price")
    if price is None:
        problems.append("no price")
    else:
        reasons = confirmations(price, old, discount, sizes, unit_prices)
        if not reasons and (unit_prices or (old is not None and discount is not None)):
            fitting = sorted(set(v for v in price_variants(price) if confirmations(v, old, discount, sizes, unit_prices)))
            if len(fitting) == 1:
                notes.append("price corrected by maths (OCR read " + f"{price:.2f}" + ")")
                price = fitting[0]
                reasons = confirmations(price, old, discount, sizes, unit_prices)
        if reasons:
            notes.extend(reasons)
        elif unit_prices:
            problems.append("price and unit price do not match")
        elif old is not None and discount is not None:
            problems.append("discount does not match prices")
        elif not product["price_sure"]:
            problems.append("price not sure (OCR)")
        else:
            notes.append("not checked: no unit price printed")
        unit_ok = "unit price fits" in reasons
        if old is not None and (old <= price or old > 10 * price):
            if unit_ok:
                notes.append("old price " + f"{old:.2f}" + " removed (does not fit the price)")
                old = None
            else:
                problems.append("old price is not higher than offer price")
        if old is not None and discount is not None and not discount_fits(price, old, discount):
            if unit_ok:
                fixed = sorted(set(v for v in price_variants(old) if discount_fits(price, v, discount)))
                if len(fixed) == 1:
                    notes.append("old price corrected by maths (OCR read " + f"{old:.2f}" + ")")
                    old = fixed[0]
                else:
                    notes.append("old price " + f"{old:.2f}" + " and -" + str(discount) + "% removed (they do not fit)")
                    old, discount = None, None
            elif "discount does not match prices" not in problems:
                problems.append("discount does not match prices")
    if not product["name"]:
        problems.append("no product text")
    return price, old, discount, problems, notes


# 1. which pages: all, or the ones typed ("1-5" or "7")
pdf = pymupdf.open(pdf_path)
page_numbers = list(range(1, pdf.page_count + 1))
if len(sys.argv) > 1:
    first_page, _, last_page = sys.argv[1].partition("-")
    if not (first_page.isdigit() and (last_page == "" or last_page.isdigit())):
        print("Type the pages like this: python netto_try/aldi_offers.py 1-5")
        exit(1)
    page_numbers = [n for n in page_numbers if int(first_page) <= n <= int(last_page or first_page)]
if not page_numbers:
    print("These pages are not in the flyer (it has", pdf.page_count, "pages)")
    exit(1)
print("Flyer:", pdf_path, "| pages:", pdf.page_count, "| reading:", page_numbers[0], "-", page_numbers[-1], "| OCR: RapidOCR")

all_products = []
all_dates = []
previous_default = None
for number in page_numbers:
    try:
        # 2. the page picture in full size; U = 1 for the usual 632-pixel-wide ALDI page (all sizes below use U)
        picture = page_picture(pdf, pdf[number - 1])
        U = picture.shape[1] / 632
        red, yellow, grey = colour_masks(picture)

        # 3. price boxes: solid red boxes (not too thin, not too wide) with big white digits inside
        boxes, strips = [], []
        for box in solid_boxes(red, U):
            width, height = box["right"] - box["left"], box["bottom"] - box["top"]
            if width >= 2.8 * height and height <= 26 * U:
                strips.append(box)                         # a thin strip, e.g. "kg-Preis"
                continue
            if not (40 * U <= width <= 240 * U and 30 * U <= height <= 200 * U and 0.7 <= width / height <= 2.8):
                continue
            result = read_price_box(grey, box, U)
            if result is not None:
                box.update(result)
                boxes.append(box)

        # 4. around every box: yellow labels on top, old price strip under it, "kg-Preis" strip
        yellow_boxes = solid_boxes(yellow, U)
        zones = []
        for box in boxes:
            box["info"] = labels_above(box, yellow_boxes, picture, U)
            box["old"], old_area = old_price_below(box, picture, U)
            box["per"], strip = per_strip(box, strips, picture, U)
            box["areas"] = box["info"]["areas"] + [area for area in [old_area, strip] if area is not None]
            zones = zones + [box] + box["areas"]

        # 5. the text lines of the page. A box whose digits could not be read: try the page reading inside the box.
        #    The lines inside price boxes and labels are not product text.
        all_lines = page_lines(picture, cache_folder + "/lines_" + str(number) + ".csv")
        for box in boxes:
            if box["price"] is not None:
                continue
            for line in all_lines:
                if box["left"] <= (line["left"] + line["right"]) / 2 <= box["right"] \
                        and box["top"] <= (line["top"] + line["bottom"]) / 2 <= box["bottom"]:
                    digits = re.sub(r"\D", "", line["text"])
                    if 3 <= len(digits) <= 5:              # "1.39**" read as "139" -> 1.39
                        box["price"] = int(digits[:-2]) + int(digits[-2:]) / 100
                        box["euros"], box["sure"] = int(digits[:-2]), False
                        box["raw"] = box["raw"] + "; page reading '" + line["text"] + "'"
                        break
        lines = [l for l in all_lines if not any(z["left"] <= (l["left"] + l["right"]) / 2 <= z["right"]
                                                 and z["top"] <= (l["top"] + l["bottom"]) / 2 <= z["bottom"] for z in zones)]
        dates = date_lines(lines)
        for date in dates:
            if date["end"] is not None:
                all_dates.append((date["start"], date["end"]))
        top_dates = [d for d in dates if d["bottom"] <= 0.12 * picture.shape[0]]
        page_default = top_dates[0] if top_dates else previous_default
        previous_default = page_default

        # 6. text blocks: every box takes the block that looks most like its product text (best match first)
        used = set()
        remaining = list(boxes)
        while remaining:
            best = None
            free_lines = [l for l in lines if id(l) not in used]
            for box in remaining:
                for layout, block in blocks_near(box, free_lines, boxes, U):
                    score = block_score(layout, block, box)
                    if score is not None and score >= 1.0 and (best is None or score > best[0]):
                        best = (score, box, block)
            if best is None:
                break
            score, box, block = best
            box["block"] = block
            used.update(id(l) for l in block)
            remaining = [b for b in remaining if b is not box]

        # 7. one product per price box
        found_text = 0
        for box in boxes:
            block = box.get("block")
            labels, brand, name, description = split_block(block) if block else ([], "", "", "")
            if name:
                found_text = found_text + 1
            info = box["info"]
            sizes = sizes_of(name + " " + description) + sizes_of(info["weight_box"])
            if box["per"] == "1 kg":
                sizes.append((1.0, "kg"))
            elif box["per"] == "100 g":
                sizes.append((0.1, "kg"))
            width = box["right"] - box["left"]
            date = None
            for d in dates:                                # the nearest date banner ABOVE the box, in its column
                if d["bottom"] <= box["top"] + 5 * U and d["left"] <= box["right"] + 1.5 * width and d["right"] >= box["left"] - 3 * width:
                    if date is None or d["bottom"] > date["bottom"]:
                        date = d
            all_products.append({
                "page": number, "brand": brand, "name": name, "description": description,
                "weight": weight_text(description) or info["weight_box"] or box["per"],
                "price": box["price"], "euros": box["euros"], "price_sure": box["sure"], "raw": box["raw"],
                "old": box["old"], "discount": info["discount"], "labels": info["labels"] + labels,
                "weight_box": info["weight_box"], "per": box["per"],
                "sizes": sizes, "unit_prices": unit_prices_of(description),
                "unit_price": " ".join(m.group() for m in re.finditer(UNIT_PRICE, description)),
                "date": date or page_default, "where": "x " + str(box["left"]) + ", y " + str(box["top"]),
            })

        # 8. a picture of what was found (to check by eye and to tune)
        check_picture = picture.copy()
        thick = max(1, round(U))
        for box in boxes:
            cv2.rectangle(check_picture, (box["left"], box["top"]), (box["right"], box["bottom"]), (255, 0, 0), 2 * thick)
            text = f"{box['price']:.2f}" if box["price"] is not None else "?"
            cv2.putText(check_picture, text, (box["left"], max(12, box["top"] - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.5 * U, (255, 0, 0), thick)
            for area in box["areas"]:
                cv2.rectangle(check_picture, (int(area["left"]), int(area["top"])), (int(area["right"]), int(area["bottom"])), (0, 140, 255), thick)
            if box.get("block"):
                left = int(min(l["left"] for l in box["block"]))
                top = int(min(l["top"] for l in box["block"]))
                right = int(max(l["right"] for l in box["block"]))
                bottom = int(max(l["bottom"] for l in box["block"]))
                cv2.rectangle(check_picture, (left, top), (right, bottom), (0, 170, 0), thick)
        cv2.imwrite(picture_folder + "/page_" + str(number) + ".png", check_picture)
        prices_read = sum(1 for box in boxes if box["price"] is not None)
        print("page", number, ":", len(boxes), "price boxes,", prices_read, "prices read,", found_text, "with product text")
    except Exception as error:
        print("ERROR on page", number, "->", repr(error))

# 9. dates: the main dates = the "Mo. 9.11. – Sa. 14.11." printed most often; none -> Monday - Saturday of the week
if all_dates:
    main_dates = max(set(all_dates), key=all_dates.count)
else:
    main_dates = (monday, monday + datetime.timedelta(days=5))

# 10. the final rows
details = []
seen = []
for product in all_products:
    price, old, discount, problems, notes = check_row(product)
    if product["date"] is None:
        start, end = main_dates
    else:
        start = product["date"]["start"]
        end = product["date"]["end"] or main_dates[1]      # "ab Do. 12.11." -> until the end of the flyer week
        end = max(end, start)
    if price is None and not product["name"]:
        status = "not an offer"
    elif any(word in " ".join(problems) for word in ["no price", "no product text", "not match", "not higher", "not sure"]):
        status = "check"
    else:
        status = "ok"
    weight = product["weight"]
    if weight == "" and product["unit_prices"] and price is not None and fits(price, [(1.0, "kg")], product["unit_prices"]):
        weight = "1 kg"                                    # loose fruit/vegetables: the price is per kg
    key = (product["brand"], product["name"], weight, price, start, end)
    if key in seen:
        continue
    seen.append(key)
    applied = old is not None or discount is not None or "AKTION" in product["labels"]

    # the description: EVERYTHING the flyer says about this product, in one text
    parts = []
    if product["description"]:
        parts.append(product["description"])
    if old is not None:
        parts.append("old price: " + f"{old:.2f}")
    if discount is not None:
        parts.append("discount: -" + str(discount) + "%")
    if product["per"]:
        parts.append("price per " + product["per"])
    if product["weight_box"]:
        parts.append("pack: " + product["weight_box"])
    if product["labels"]:
        parts.append("labels: " + ", ".join(product["labels"]))
    parts.append("page: " + str(product["page"]))

    details.append({
        "week": week, "store": STORE, "page": product["page"],
        "offer_start_date": start.isoformat(), "offer_end_date": end.isoformat(),
        "brand": product["brand"] or "UNKNOWN", "product_name": product["name"], "product_weight": weight,
        "price_eur": f"{price:.2f}" if price is not None else "",
        "offer_applied": "yes" if applied else "no",
        "app_or_card_price": "no",
        "description": " | ".join(parts),
        "old_price_eur": f"{old:.2f}" if old is not None else "",
        "discount_pct": discount if discount is not None else "",
        "unit_price": product["unit_price"],
        "status": status, "problems": "; ".join(problems), "notes": "; ".join(notes),
        "price_read": product["raw"], "box_place": product["where"],
    })

# 11. save the files
if len(details) == 0:
    print("No products found - look at data/review/aldi/pages/page_1.png (blue boxes = price boxes found)")
    exit(1)
SIMPLE_COLUMNS = ["week", "store", "offer_start_date", "offer_end_date", "brand", "product_name",
                  "product_weight", "price_eur", "offer_applied", "app_or_card_price", "description"]
good = [d for d in details if d["status"] == "ok"]
for d in good:
    for column in SIMPLE_COLUMNS:
        if str(d[column]).strip() == "":
            d[column] = "UNKNOWN"                          # no empty cells (e.g. no size on a non-food product)
with open("data/output/offers_aldi.csv", "w", newline="", encoding="utf-8-sig") as file:
    writer = csv.DictWriter(file, fieldnames=SIMPLE_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(good)
with open("data/review/aldi/needs_review.csv", "w", newline="", encoding="utf-8-sig") as file:
    writer = csv.DictWriter(file, fieldnames=details[0].keys())
    writer.writeheader()
    writer.writerows([d for d in details if d["status"] == "check"])
with open("data/review/aldi/all_offers.csv", "w", newline="", encoding="utf-8-sig") as file:
    writer = csv.DictWriter(file, fieldnames=details[0].keys())
    writer.writeheader()
    writer.writerows(details)

checked = sum(1 for d in good if "fit" in d["notes"] and "not checked" not in d["notes"])
corrected = sum(1 for d in good if "corrected by maths" in d["notes"] or "cents from" in d["notes"])
reasons = {}
for d in details:
    if d["status"] == "check":
        for problem in d["problems"].split("; "):
            reasons[problem] = reasons.get(problem, 0) + 1
print("Week:", week, "| main dates:", main_dates[0], "-", main_dates[1])
print("Products found:", len(all_products), "| after removing repeats:", len(details))
print("  ok:", len(good), "(" + str(checked) + " confirmed by the maths,", corrected, "OCR digits corrected by the maths)")
print("  needs review:", sum(1 for d in details if d["status"] == "check"), "-> data/review/aldi/needs_review.csv")
print("     why:", reasons)
print("  not an offer:", sum(1 for d in details if d["status"] == "not an offer"))
print("Check pictures: data/review/aldi/pages/page_N.png")
print("Done! data/output/offers_aldi.csv (11 columns: the 10 Kaufland columns + description)")
# Stage 4: read every page  -  version 3: Kaufland + Netto
# We save not only WHAT the text says, but also HOW it looks, plus the boxes on the page:
#   kaufland()  -> data/text/kaufland/page_N.csv + boxes_N.csv
#   netto()     -> data/text/netto/page_N.csv + boxes_N.csv + lines_N.csv
#                  (lines: Netto CROSSES OUT its old prices with a thin line, so Netto needs them too)
#   page_N.csv   -> every piece of text: where it is + font, size, colour
#   boxes_N.csv  -> every box on the page: where it is + fill colour + border colour
# At the bottom, every store in config/settings.yaml is run. If Netto fails, Kaufland still goes on.

import os
import csv
import glob
import pymupdf
import storage


# =====================================================================================================
# KAUFLAND
# =====================================================================================================
def color_text(color):
    """(0.92, 0.1, 0.15) -> '#eb1a26'   (None = no colour -> '')"""
    if color is None or len(color) != 3:
        return ""
    red, green, blue = color
    return "#%02x%02x%02x" % (round(red * 255), round(green * 255), round(blue * 255))


def kaufland():
    """Kaufland: every page -> page_N.csv + boxes_N.csv in data/text/kaufland  (the code as before)"""
    pdf_path = storage.flyer_path("kaufland")       # the flyer of the week we work on: data/flyers/kaufland/kaufland_2026-W46.pdf
    output_folder = "data/text/kaufland"
    os.makedirs(output_folder, exist_ok=True)

    # delete the files of the last flyer first
    # (otherwise a 70-page flyer leaves page_9 ... page_70 behind when the next flyer has only 8 pages)
    for old_file in glob.glob(output_folder + "/*.csv"):
        os.remove(old_file)

    pdf = pymupdf.open(pdf_path)
    for page in pdf:
        page_number = page.number + 1

        # 1. text pieces. A "piece" is text with ONE look: e.g. "SAINT ALBRAY" in Kaufland-Bold+ size 8
        pieces = []
        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block:                        # a picture block has no text
                continue
            line_number = 0
            for line in block["lines"]:
                line_number = line_number + 1
                for span in line["spans"]:
                    if span["text"].strip() == "":          # only spaces -> skip
                        continue
                    left, top, right, bottom = span["bbox"]
                    pieces.append([span["text"], round(left, 1), round(top, 1), round(right, 1), round(bottom, 1),
                                   span["font"], round(span["size"], 1), "#%06x" % span["color"],
                                   block["number"], line_number])

        with open(output_folder + "/page_" + str(page_number) + ".csv", "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["text", "left", "top", "right", "bottom", "font", "size", "color", "block", "line"])
            writer.writerows(pieces)

        # 2. boxes: every drawn shape that is not tiny (price boxes, label boxes, backgrounds, ...)
        boxes = []
        for drawing in page.get_drawings():
            box = drawing["rect"]
            if box.width < 10 or box.height < 8:            # thin lines and dots are not boxes
                continue
            fill = color_text(drawing.get("fill"))          # colour inside the box
            border = color_text(drawing.get("color"))       # colour of the outline
            if fill == "" and border == "":
                continue
            boxes.append([round(box.x0, 1), round(box.y0, 1), round(box.x1, 1), round(box.y1, 1), fill, border])

        with open(output_folder + "/boxes_" + str(page_number) + ".csv", "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["left", "top", "right", "bottom", "fill", "border"])
            writer.writerows(boxes)

        print("Page", page_number, "-", len(pieces), "text pieces,", len(boxes), "boxes saved")
    pdf.close()


# =====================================================================================================
# NETTO
# =====================================================================================================
def netto_color_text(color):
    """(0.93, 0.3, 0.61) -> '#ee4d9b'   (None = no colour -> '')"""
    if color is None or len(color) != 3:
        return ""
    red, green, blue = color
    return "#%02x%02x%02x" % (round(red * 255), round(green * 255), round(blue * 255))


def netto():
    """Netto: every page -> page_N.csv + boxes_N.csv + lines_N.csv in data/text/netto"""
    pdf_path = storage.flyer_path("netto")          # the flyer of the week we work on: data/flyers/netto/netto_2026-W46.pdf
    output_folder = "data/text/netto"
    os.makedirs(output_folder, exist_ok=True)
    for old_file in glob.glob(output_folder + "/*.csv"):     # the files of the last flyer
        os.remove(old_file)

    pdf = pymupdf.open(pdf_path)
    for page in pdf:
        page_number = page.number + 1

        # 1. text pieces: text with ONE look, e.g. "Knorr Suppenliebe" in FrankfurterEF size 10
        pieces = []
        for block in page.get_text("dict")["blocks"]:
            if "lines" not in block:                        # a picture block has no text
                continue
            line_number = 0
            for line in block["lines"]:
                line_number = line_number + 1
                for span in line["spans"]:
                    if span["text"].strip() == "":          # only spaces -> skip
                        continue
                    left, top, right, bottom = span["bbox"]
                    pieces.append([span["text"], round(left, 1), round(top, 1), round(right, 1), round(bottom, 1),
                                   span["font"], round(span["size"], 1), "#%06x" % span["color"],
                                   block["number"], line_number])
        with open(output_folder + "/page_" + str(page_number) + ".csv", "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["text", "left", "top", "right", "bottom", "font", "size", "color", "block", "line"])
            writer.writerows(pieces)

        # 2. boxes (price boxes, discount boxes, ...) and thin lines (the line through a crossed-out old price "4.99")
        boxes = []
        thin_lines = []
        for drawing in page.get_drawings():
            box = drawing["rect"]
            if box.height <= 2.5 and 5 <= box.width <= 60:
                thin_lines.append([round(box.x0, 1), round(box.y0, 1), round(box.x1, 1), round(box.y1, 1)])
            if box.width < 10 or box.height < 8:            # thin lines and dots are not boxes
                continue
            fill = netto_color_text(drawing.get("fill"))
            border = netto_color_text(drawing.get("color"))
            if fill == "" and border == "":
                continue
            boxes.append([round(box.x0, 1), round(box.y0, 1), round(box.x1, 1), round(box.y1, 1), fill, border])
        with open(output_folder + "/boxes_" + str(page_number) + ".csv", "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["left", "top", "right", "bottom", "fill", "border"])
            writer.writerows(boxes)
        with open(output_folder + "/lines_" + str(page_number) + ".csv", "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file)
            writer.writerow(["left", "top", "right", "bottom"])
            writer.writerows(thin_lines)

        print("Page", page_number, "-", len(pieces), "text pieces,", len(boxes), "boxes,", len(thin_lines), "thin lines saved")
    pdf.close()


# =====================================================================================================
# RUN every store of config/settings.yaml with its own function (kaufland() and netto() above)
# (only when started as a program - python pipeline/ocr.py - not when the tests read this file)
# =====================================================================================================
if __name__ == "__main__":
    STORE_PARTS = {"kaufland": kaufland, "netto": netto}
    for store in storage.stores():
        if store not in STORE_PARTS:
            print("\n" + store + ": ocr.py has no function for this store yet - skipped")
            continue
        if not os.path.exists("data/pages/" + store + "/manifest.csv"):
            print("\n" + store + ": nothing new to read (week already done, no flyer, or preprocess failed) - skipped")
            continue
        print("\n----- " + store + ":", storage.flyer_path(store), "-----")
        try:
            STORE_PARTS[store]()
        except Exception as error:
            storage.store_failed(store, "ocr", error)
# Stage 4: read every page  -  version 2
# Now we save not only WHAT the text says, but also HOW it looks, plus the boxes on the page:
#   data/text/kaufland/page_N.csv   -> every piece of text: where it is + font, size, colour
#   data/text/kaufland/boxes_N.csv  -> every box on the page: where it is + fill colour + border colour

import os
import csv
import glob
import pymupdf
import storage

pdf_path = storage.flyer_path()     # this week's flyer: data/flyers/kaufland/kaufland_2026-W46.pdf
output_folder = "data/text/kaufland"
os.makedirs(output_folder, exist_ok=True)

# delete the files of the last flyer first
# (otherwise a 70-page flyer leaves page_9 ... page_70 behind when the next flyer has only 8 pages)
for old_file in glob.glob(output_folder + "/*.csv"):
    os.remove(old_file)


def color_text(color):
    """(0.92, 0.1, 0.15) -> '#eb1a26'   (None = no colour -> '')"""
    if color is None or len(color) != 3:
        return ""
    red, green, blue = color
    return "#%02x%02x%02x" % (round(red * 255), round(green * 255), round(blue * 255))


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
# ingest.py (stage 1 of 8) - downloads this week's flyers, every store into its own folder
#
# How it works:
#   Kaufland, Netto, Lidl and ALDI Nord -> data/flyers/<store>/<store>_2026-W47.pdf   (ALDI is only collected for now)
#   python pipeline/ingest.py       the week of tomorrow (on Sunday = next week); a flyer that is already there is skipped
#   python pipeline/ingest.py 46    week 46, always downloaded again
#   A store that fails shows up in the SUMMARY - the run goes on with the flyers you already have.
#
# Tried and tuned:
#   - Kaufland and Lidl use the same flyer system (leaflets.schwarz) -> its data address gives the PDF link for both
#   - the Lidl flyer name ends with a random code, so it can't be guessed -> it is looked up in Lidl's flyer list first
#   - ALDI's viewer has no PDF link -> the page pictures are put into one PDF (no text inside, it needs OCR later)
#   - REWE is on hold

import os
import re
import sys
import datetime
import urllib.request
import urllib.error
import urllib.parse
import pymupdf
import storage

# the flyer addresses of every store; {week} is filled in (46). The addresses are tried one after another.
STORES = {
    "kaufland": [
        # the data address behind the flyer page (Kaufland's flyer system, the same one Lidl uses)
        "https://endpoints.leaflets.schwarz/v4/flyer?flyer_identifier=DE_de_KDZ1_3000_D{week}&region_id=0&region_code=0",
        # the flyer page itself (your region: 3000)
        "https://leaflets.kaufland.com/de-DE/DE_de_KDZ1_3000_D{week}/ar/3000",
    ],
    "netto": [
        # the flyer page (your store: 5217)
        "https://wochenprospekt.netto-online.de/hz{week}_cosb/?storeid=5217",
    ],
    "lidl": [
        # {name} = this week's Lidl flyer name, e.g. aktionsprospekt-09-11-2026-14-11-2026-de787e (looked up first, see LIDL_LISTS)
        # the data address behind the flyer page (same flyer system as Kaufland) - its answer contains the PDF link
        "https://endpoints.leaflets.schwarz/v4/flyer?flyer_identifier={name}&region_id=0",
        # the flyer page itself
        "https://www.lidl.de/l/prospekte/{name}/ar/0",
    ],
    "aldi": [
        # ALDI Nord's flyer viewer (iPaper). The address has the year, the week and the Monday: ...2026cw46...ab-montag-09-11/
        # ALDI sometimes adds "-2" at the end, so both are tried. If no PDF link is found, the page pictures are used (see below).
        "https://magazine.aldi-nord.de/aldi-nord/aldi-aktuell/{year}/{year}cw{week}mopromotionaldi-angebote-ab-montag-{monday}/",
        "https://ipaper.ipapercms.dk/aldi-nord/aldi-aktuell/{year}/{year}cw{week}mopromotionaldi-angebote-ab-montag-{monday}/",
        "https://magazine.aldi-nord.de/aldi-nord/aldi-aktuell/{year}/{year}cw{week}mopromotionaldi-angebote-ab-montag-{monday}-2/",
        "https://ipaper.ipapercms.dk/aldi-nord/aldi-aktuell/{year}/{year}cw{week}mopromotionaldi-angebote-ab-montag-{monday}-2/",
    ],
}
# Lidl's flyer name ends with a random code ("...-de787e"), so it can not be guessed like Kaufland's week number.
# It is looked up in Lidl's lists of all current flyers (tried one after another):
LIDL_LISTS = [
    "https://endpoints.leaflets.schwarz/v4/overview/?region_id=0&client_locale=lidl/de-DE",   # the data list behind the page below
    "https://www.lidl.de/c/online-prospekte/s10005610",                                       # Lidl's "Online-Prospekte" page
]
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


def download(url, show_errors=True):
    """get one web address -> its content (None if it fails; the reason is printed)"""
    try:
        request = urllib.request.Request(url, headers=BROWSER)
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if show_errors:
            print("   ->", error.code, error.reason, "(403 = not allowed, 404 = not there, maybe not published yet)")
    except Exception as error:
        if show_errors:
            print("   -> failed:", error)
    return None


def find_pdf_links(content, page_url):
    """every web address ending in .pdf inside a page or data file
    (full links "https://.../x.pdf" and short links "/100989/.../x.pdf", which belong to the page's website)"""
    text = content.decode("utf-8", errors="ignore")
    text = text.replace("\\/", "/").replace("\\u0026", "&").replace("&amp;", "&")   # how pages write / and &
    links = []
    for link in re.findall(r"https?://[^\"'\s<>]+?\.pdf(?:\?[^\"'\s<>]*)?", text):
        if link not in links:
            links.append(link)
    for short in re.findall(r"[\"'(=](/[^\"'\s<>()]+?\.pdf(?:\?[^\"'\s<>]*)?)", text):
        link = urllib.parse.urljoin(page_url, short)     # "/100989/..." -> "https://wochenprospekt.netto-online.de/100989/..."
        if link not in links:
            links.append(link)
    return links


def get_pdf(addresses, log_name):
    """try the addresses one after another: the address itself may be the PDF, or a page with PDF links on it
    -> the PDF (or None; then the answers are saved in logs/ so Claude can look at them)"""
    answers = []
    for url in addresses:
        print("   trying", url)
        content = download(url)
        if content is None:
            continue
        if content[:4] == b"%PDF":                         # every real PDF file starts with %PDF
            return content
        answers.append(content)
        links = find_pdf_links(content, url)
        print("   -> answer received,", len(links), "PDF link(s) found")
        for link in links:
            print("      downloading", link)
            pdf = download(link)
            if pdf is not None and pdf[:4] == b"%PDF":
                return pdf
    os.makedirs("logs", exist_ok=True)
    for number in range(len(answers)):
        with open("logs/" + log_name + "_" + str(number + 1) + ".txt", "wb") as file:
            file.write(answers[number])
    if answers:
        print("   -> no PDF found; the answers are saved in logs/" + log_name + "_*.txt (send them to Claude)")
    return None


def find_lidl_name(year, week_number):
    """look up this week's Lidl flyer name in Lidl's flyer lists
    'aktionsprospekt-09-11-2026-14-11-2026-de787e' -> its first day (09.11.2026) must be in the week we want
    -> the name (or None; then the lists are saved in logs/ so Claude can look at them)"""
    answers = []
    for url in LIDL_LISTS:
        print("   looking for the flyer name in", url)
        content = download(url)
        if content is None:
            continue
        answers.append(content)
        text = content.decode("utf-8", errors="ignore")
        for found in re.finditer(r"aktionsprospekt-(\d\d)-(\d\d)-(\d{4})-\d\d-\d\d-\d{4}(-[0-9a-z]+)?", text):
            try:
                first_day = datetime.date(int(found.group(3)), int(found.group(2)), int(found.group(1)))
            except ValueError:                                # not a real date -> ignore it
                continue
            first_year, first_week, first_weekday = first_day.isocalendar()
            if first_year == year and first_week == week_number:
                print("   -> found:", found.group(0))
                return found.group(0)
    os.makedirs("logs", exist_ok=True)
    for number in range(len(answers)):
        with open("logs/ingest_lidl_list_" + str(number + 1) + ".txt", "wb") as file:
            file.write(answers[number])
    print("   -> no Lidl flyer for this week in the lists (maybe not published yet)")
    if answers:
        print("   -> the lists are saved in logs/ingest_lidl_list_*.txt (send them to Claude)")
    return None


def pdf_from_pictures(flyer_address):
    """ALDI's flyer viewer shows every page as a picture: <flyer address>Image.ashx?PageNumber=1, 2, 3, ...
    -> all pictures put into ONE PDF (or None if there is no picture)
    note: a PDF made of pictures has no text inside - reading it later needs OCR (Tesseract)"""
    print("   trying the page pictures of", flyer_address)
    flyer = pymupdf.open()                                 # a new, empty PDF
    previous = None
    for number in range(1, 201):                           # at most 200 pages
        picture = download(flyer_address + "Image.ashx?PageNumber=" + str(number) + "&ImageType=Normal", show_errors=False)
        if picture is None or picture == previous:         # no more pages (or the last page again)
            break
        if picture[:2] == b"\xff\xd8":                     # every JPG picture starts like this
            kind = "jpg"
        elif picture[:4] == b"\x89PNG":                    # every PNG picture starts like this
            kind = "png"
        else:                                              # not a picture (e.g. an error page)
            break
        one_page = pymupdf.open(stream=picture, filetype=kind)
        flyer.insert_pdf(pymupdf.open("pdf", one_page.convert_to_pdf()))
        previous = picture
    if flyer.page_count == 0:
        print("   -> no page pictures there")
        return None
    print("   -> made one PDF from", flyer.page_count, "page pictures")
    return flyer.tobytes()


# 1. which week? the week of TOMORROW (a run on Sunday gets Monday's new flyers), or the number you typed
today = datetime.date.today()
if len(sys.argv) > 1:
    year, week_number = today.year, int(sys.argv[1])
else:
    year, week_number, weekday = (today + datetime.timedelta(days=1)).isocalendar()
if week_number < 1 or week_number > 53:
    print("There is no week", week_number, "- type a number from 1 to 53, e.g.: python pipeline/ingest.py 47")
    exit(1)
week = str(year) + "-W" + str(week_number).zfill(2)
print("Week:", week)

# 2. every store: skip if already there, else download it into the store's folder
results = {}
for store, addresses in STORES.items():
    print("\n" + store.upper())
    target = storage.flyers_folder(store) + "/" + store + "_" + week + ".pdf"
    if len(sys.argv) == 1 and os.path.exists(target):
        print("   already there - nothing to download")
        results[store] = "already there"
        continue
    name = ""
    if store == "lidl":                                # Lidl: look up this week's flyer name first
        name = find_lidl_name(year, week_number)
        if name is None:
            results[store] = "FAILED"
            continue
    monday = datetime.date.fromisocalendar(year, week_number, 1).strftime("%d-%m")     # week 46 -> "09-11"
    week_addresses = [address.format(week=str(week_number).zfill(2), name=name, year=year, monday=monday) for address in addresses]
    pdf = get_pdf(week_addresses, "ingest_" + store)
    if pdf is None and store == "aldi":                # ALDI: no PDF link found -> use the page pictures
        for address in week_addresses:
            pdf = pdf_from_pictures(address)
            if pdf is not None:
                break
    if pdf is None:
        results[store] = "FAILED"
        continue
    with open(target, "wb") as file:
        file.write(pdf)
    print("   -> saved:", target, "(" + str(round(len(pdf) / 1_000_000, 1)) + " MB)")
    results[store] = "downloaded"
    storage.delete_old_flyers(store)                   # keep only the newest weeks of this store

# 3. summary: did every store work?
print("\nSUMMARY", week + ":", ", ".join(store + " " + result for store, result in results.items()))
if "FAILED" in results.values():
    exit(1)
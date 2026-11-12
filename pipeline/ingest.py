# Stage 0: download this week's flyers of ALL stores, each store into its own folder
#   Kaufland -> data/flyers/kaufland/kaufland_2026-W46.pdf   (the pipeline reads this one)
#   Netto    -> data/flyers/netto/netto_2026-W46.pdf         (collected for later - no Netto rules yet)
#   only the newest 4 weeks of each store are kept (keep_weeks in config/settings.yaml)
# Run:
#     python pipeline/ingest.py          -> this week (run on Sunday -> next week's flyers),
#                                           a flyer that is already downloaded is skipped
#     python pipeline/ingest.py 46       -> week 46, ALWAYS downloaded (good for testing)
#     python pipeline/ingest.py "https://..."   -> TEST MODE: download ANY address into data/flyers/test/

import os
import re
import sys
import datetime
import urllib.request
import urllib.error
import urllib.parse
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
}
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"}


def download(url):
    """get one web address -> its content (None if it fails; the reason is printed)"""
    try:
        request = urllib.request.Request(url, headers=BROWSER)
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        print("   ->", error.code, error.reason, "(403 = not allowed, 404 = not there, maybe not published yet)")
    except Exception as error:
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


# 0. TEST MODE: an address was typed -> download it into data/flyers/test/ (never read by the pipeline)
if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
    print("TEST MODE:", sys.argv[1])
    pdf = get_pdf([sys.argv[1]], "ingest_test")
    if pdf is None:
        exit(1)
    test_file = storage.flyers_folder("test") + "/test_flyer.pdf"
    with open(test_file, "wb") as file:
        file.write(pdf)
    print("Done! Download works. Saved:", test_file, "(" + str(round(len(pdf) / 1_000_000, 1)) + " MB)")
    exit(0)

# 1. which week? the week of TOMORROW (a run on Sunday gets Monday's new flyers), or the number you typed
today = datetime.date.today()
if len(sys.argv) > 1:
    year, week_number = today.year, int(sys.argv[1])
else:
    year, week_number, weekday = (today + datetime.timedelta(days=1)).isocalendar()
week = str(year) + "-W" + str(week_number).zfill(2)
print("Week:", week)

# 2. every store: skip if already there, else download it into the store's folder
results = {}
for store, addresses in STORES.items():
    print("\n" + store.upper())
    storage.move_old_flyers(store)                     # one time: flyers from the old folders inbox/ and raw/
    target = storage.flyers_folder(store) + "/" + store + "_" + week + ".pdf"
    if len(sys.argv) == 1 and os.path.exists(target):
        print("   already there - nothing to download")
        results[store] = "already there"
        continue
    week_addresses = [address.format(week=str(week_number).zfill(2)) for address in addresses]
    pdf = get_pdf(week_addresses, "ingest_" + store)
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
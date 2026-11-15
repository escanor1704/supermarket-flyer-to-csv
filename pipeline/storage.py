# storage.py: the ONE place that knows where every file goes - the same for every store
#   stores()          ->  ['kaufland', 'netto']                    (the stores in config/settings.yaml)
#   flyers_folder()   ->  data/flyers/netto                        (all weekly flyers of a store)
#   flyer_path()      ->  data/flyers/netto/netto_2026-W46.pdf     (the flyer of the week the pipeline works on)
#   weekly_file()     ->  data/output/offers_2026-W46.csv          (the final file of one week, all stores)
#   already_done()    ->  True if that week's file already has the store -> it is not run again
#   store_failed()    ->  Netto fails: skipped, Kaufland goes on   (Kaufland fails: the run stops)
# Nothing about how a flyer LOOKS is here: that is in the kaufland() and netto() functions of every stage.
# Check it yourself:  python pipeline/storage.py

import os
import re
import csv
import glob
import traceback
import yaml

SETTINGS_FILE = "config/settings.yaml"


def settings():
    """read config/settings.yaml -> {'stores': ['kaufland', 'netto'], 'data_folder': 'data', 'keep_weeks': 4}"""
    with open(SETTINGS_FILE, encoding="utf-8") as file:
        return yaml.safe_load(file)


def stores():
    """the stores the pipeline reads, in order: ['kaufland', 'netto']  (the first one is the main store)"""
    return settings()["stores"]


def store_failed(store, stage, error):
    """One store's part of a stage crashed.
    The main store (the first in settings.yaml) stops the run, like before.
    Any other store is only skipped for the rest of this run, so a Netto problem never stops Kaufland."""
    if store == stores()[0]:
        raise error
    traceback.print_exc()                                  # the error lines (send them to Claude)
    print("\nWARNING:", store, "failed in", stage, "->", error)
    print("        ", store, "is skipped for the rest of this run - the other stores go on")


def flyers_folder(store=None):
    """the folder with all weekly flyers of one store, e.g. data/flyers/kaufland (made if it does not exist)"""
    if store is None:
        store = stores()[0]
    path = settings()["data_folder"] + "/flyers/" + store
    os.makedirs(path, exist_ok=True)
    return path


def week_of(file_name):
    """'kaufland_2026-W46.pdf' -> '2026-W46'   (None if the name has no week)"""
    match = re.search(r"_(\d{4}-W\d\d)\.pdf$", file_name)
    if match:
        return match.group(1)
    return None


def weekly_flyers(store=None):
    """the flyers with a week in their name, oldest first: ['netto_2026-W45.pdf', 'netto_2026-W46.pdf']"""
    names = [name for name in os.listdir(flyers_folder(store)) if week_of(name)]
    return sorted(names)


def newest_flyer(store=None):
    """the newest flyer of a store: data/flyers/netto/netto_2026-W47.pdf   (None if the store has no flyer)"""
    flyers = weekly_flyers(store)
    if len(flyers) == 0:
        return None
    return flyers_folder(store) + "/" + flyers[-1]


def delete_old_flyers(store=None):
    """keep only the newest weeks of flyers (keep_weeks in config/settings.yaml)"""
    keep = settings()["keep_weeks"]
    for name in weekly_flyers(store)[:-keep]:
        os.remove(flyers_folder(store) + "/" + name)
        print("Deleted old flyer", name)


def move_old_flyers(store=None):
    """ONE TIME: flyers from the old folders (data/inbox/kaufland, data/raw/kaufland/2026-W46) -> data/flyers/kaufland"""
    s = settings()
    if store is None:
        store = stores()[0]
    target = flyers_folder(store)
    old_files = glob.glob(s["data_folder"] + "/inbox/" + store + "/*.pdf") + glob.glob(s["data_folder"] + "/raw/" + store + "/*.pdf")
    for pdf in old_files:
        os.replace(pdf, target + "/" + os.path.basename(pdf))
        print("Moved", pdf, "->", target)
    for pdf in glob.glob(s["data_folder"] + "/raw/" + store + "/*/offers.pdf"):
        week = os.path.basename(os.path.dirname(pdf))       # data/raw/kaufland/2026-W46/offers.pdf -> 2026-W46
        if re.fullmatch(r"\d{4}-W\d\d", week):
            os.replace(pdf, target + "/" + store + "_" + week + ".pdf")
            print("Moved", pdf, "->", target + "/" + store + "_" + week + ".pdf")


def output_folder():
    """the final files of ALL weeks together: data/output"""
    path = settings()["data_folder"] + "/output"
    os.makedirs(path, exist_ok=True)
    return path


def weekly_file(week):
    """the final file of one week, all stores together: data/output/offers_2026-W46.csv"""
    return output_folder() + "/offers_" + week + ".csv"


def already_done(store, week):
    """True if the final file of this week already has offers of this store
    -> that flyer was done in an earlier run and is not run again (to make it again: delete the weekly file)"""
    path = weekly_file(week)
    if not os.path.exists(path):
        return False
    with open(path, encoding="utf-8-sig") as file:
        for row in csv.DictReader(file):
            if row.get("store") == store:
                return True
    return False


def save_current_week(week):
    """remember the week the pipeline is working on now, e.g. '2026-W46' (preprocess.py does this for every new week;
    after the run it is the newest week - GitHub names the weekly file in Backblaze with it)"""
    with open(settings()["data_folder"] + "/current_week.txt", "w", encoding="utf-8") as file:
        file.write(week)


def current_week():
    """the week the pipeline is working on, e.g. '2026-W46'"""
    week_file = settings()["data_folder"] + "/current_week.txt"
    if not os.path.exists(week_file):
        print("No week yet - put the flyer in", flyers_folder(), "and run: python run.py")
        exit(1)
    with open(week_file, encoding="utf-8") as file:
        return file.read().strip()


def flyer_path(store=None, week=None):
    """the flyer of one store and week: data/flyers/netto/netto_2026-W46.pdf
    (default: the main store, and the week the pipeline is working on now)"""
    if store is None:
        store = stores()[0]
    if week is None:
        week = current_week()
    return flyers_folder(store) + "/" + store + "_" + week + ".pdf"


# python pipeline/storage.py -> shows the settings, the flyers and the week the pipeline works on
if __name__ == "__main__":
    print("Settings:     ", settings())
    for store in stores():
        print("Flyers of", store + ":", weekly_flyers(store), "-> newest:", newest_flyer(store))
    if os.path.exists(settings()["data_folder"] + "/current_week.txt"):
        print("Week of the last run:", current_week())
    else:
        print("Week of the last run: none yet (run the pipeline once)")
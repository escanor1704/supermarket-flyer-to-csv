# storage.py: the ONE place that knows where every file goes
#   flyers_folder()  ->  data/flyers/kaufland                        (all weekly flyers of a store)
#   flyer_path()     ->  data/flyers/kaufland/kaufland_2026-W46.pdf  (the flyer the pipeline works on)
# Check it yourself:  python pipeline/storage.py

import os
import re
import glob
import yaml

SETTINGS_FILE = "config/settings.yaml"


def settings():
    """read config/settings.yaml -> {'store': 'kaufland', 'data_folder': 'data', 'keep_weeks': 4, ...}"""
    with open(SETTINGS_FILE, encoding="utf-8") as file:
        return yaml.safe_load(file)


def flyers_folder(store=None):
    """the folder with all weekly flyers of one store, e.g. data/flyers/kaufland (made if it does not exist)"""
    s = settings()
    if store is None:
        store = s["store"]
    path = s["data_folder"] + "/flyers/" + store
    os.makedirs(path, exist_ok=True)
    return path


def week_of(file_name):
    """'kaufland_2026-W46.pdf' -> '2026-W46'   (None if the name has no week)"""
    match = re.search(r"_(\d{4}-W\d\d)\.pdf$", file_name)
    if match:
        return match.group(1)
    return None


def weekly_flyers(store=None):
    """the flyers with a week in their name, oldest first: ['kaufland_2026-W45.pdf', 'kaufland_2026-W46.pdf']"""
    names = [name for name in os.listdir(flyers_folder(store)) if week_of(name)]
    return sorted(names)


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
        store = s["store"]
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


def save_current_week(week):
    """remember which week the pipeline is working on, e.g. '2026-W46' (preprocess.py does this)"""
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


def flyer_path(week=None):
    """the flyer of one week: data/flyers/kaufland/kaufland_2026-W46.pdf (default: the week the pipeline works on)"""
    if week is None:
        week = current_week()
    return flyers_folder() + "/" + settings()["store"] + "_" + week + ".pdf"


# python pipeline/storage.py -> shows the settings, the flyers and the week the pipeline works on
if __name__ == "__main__":
    print("Settings:     ", settings())
    print("Flyers folder:", flyers_folder())
    print("Flyers:       ", weekly_flyers())
    if os.path.exists(settings()["data_folder"] + "/current_week.txt"):
        print("Current week: ", current_week())
        print("This flyer:   ", flyer_path())
    else:
        print("Current week:  none yet (run the pipeline once)")
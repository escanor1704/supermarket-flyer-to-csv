# Run the whole pipeline with one command
#   python run.py              -> runs all stages: download -> read -> check -> final file -> report -> clean-up
#   python run.py structure    -> starts at "structure" (uses the saved work files of the last run)

import os
import sys
import shutil
import subprocess
import time

# the stages in order: (name, file)
STAGES = [
    ("ingest",     "pipeline/ingest.py"),       # download this week's flyer -> data/flyers/kaufland
    ("preprocess", "pipeline/preprocess.py"),   # newest flyer -> page pictures + manifest
    ("ocr",        "pipeline/ocr.py"),          # pages -> text pieces + boxes
    ("structure",  "pipeline/structure.py"),    # text -> offers
    ("validate",   "pipeline/validate.py"),     # clean + check
    ("verify",     "pipeline/verify.py"),       # deep verification: repair, sort out, set aside
    ("load",       "pipeline/load.py"),         # add to data/output/offers.csv
    ("evaluate",   "pipeline/evaluate.py"),     # quality report -> logs/quality_report.txt
]

# clean-up at the end of a run: only these files are kept
KEEP_WORK_FILES = False                       # True = keep ALL work files (e.g. when Claude asks for page_N.csv)
KEEP_IN_OUTPUT = ["offers.csv"]               # data/output: the final file
KEEP_IN_REVIEW = ["needs_review.csv"]         # data/review/kaufland: the offers you should look at
WORK_FOLDERS = ["data/pages", "data/text", "data/offers"]     # made again by every run

names = []
for name, file in STAGES:
    names.append(name)

# 1. where to start? (default: the first stage)
start = names[0]
if len(sys.argv) > 1:
    start = sys.argv[1]
if start not in names:
    print("Unknown stage:", start, "- choose one of:", ", ".join(names))
    sys.exit(1)
# the stages after preprocess need the work files of the last run - the clean-up may have deleted them
if names.index(start) > names.index("preprocess") and not os.path.exists("data/pages/kaufland"):
    print("The work files of the last run were deleted by the clean-up - run everything: python run.py")
    sys.exit(1)

# 2. run the stages one after another
started = False
total_start = time.time()
for name, file in STAGES:
    if name == start:
        started = True
    if not started:
        print("skip", name, "(using its saved results)")
        continue

    print("\n========== Stage:", name, "==========")
    stage_start = time.time()
    result = subprocess.run([sys.executable, file])      # same as typing: python pipeline/....py
    seconds = round(time.time() - stage_start, 1)

    if result.returncode != 0 and name == "ingest":
        # a failed download does not stop the run: it goes on with the newest flyer you already have
        print("WARNING: not every download worked (see SUMMARY above) - going on with the newest flyer you have")
    elif result.returncode != 0:                         # 0 = everything fine, anything else = error
        print("\nSTOPPED: stage", name, "failed after", seconds, "seconds.")
        print("Fix the error above, then continue with:  python run.py", name)
        sys.exit(1)                                      # (no clean-up: the work files stay for the restart)
    print("---", name, "finished in", seconds, "seconds")

# 3. clean-up: delete the work files, keep only the final file and the offers to check
if KEEP_WORK_FILES:
    print("\nClean-up: skipped (KEEP_WORK_FILES = True) - all work files are kept")
else:
    try:
        for folder in WORK_FOLDERS:
            if os.path.exists(folder):
                shutil.rmtree(folder)
        for folder, keep in [("data/output", KEEP_IN_OUTPUT), ("data/review/kaufland", KEEP_IN_REVIEW)]:
            if not os.path.exists(folder):
                continue
            for file_name in os.listdir(folder):
                if file_name not in keep and os.path.isfile(folder + "/" + file_name):
                    os.remove(folder + "/" + file_name)
        print("\nClean-up: done. Kept data/output/offers.csv and data/review/kaufland/needs_review.csv")
    except PermissionError as error:
        print("\nClean-up: could not delete", error.filename, "- is it open (e.g. in Excel)? Close it, the next run cleans up.")

print("\nAll done in", round(time.time() - total_start, 1), "seconds. Final file: data/output/offers.csv")
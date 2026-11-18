# run.py - runs the whole pipeline with one command
#
# How it works:
#   python run.py             download -> which weeks are new? -> for every new week: read, check, save -> report -> clean-up
#   python run.py structure   start again at one stage (for the week of the last run), e.g. after fixing an error
#   The result is one CSV file per week in data/output (offers_2026-W47.csv) with all stores together.
#   A week that is already there is skipped. To make a week again, delete its file and run again.
#   If Kaufland fails the run stops; if Netto or Lidl fails, they are skipped and the rest goes on.
#
# Tried and tuned:
#   - the weekly run was a Windows Task Scheduler job on my PC -> now GitHub Actions runs it every Sunday
#   - all weeks were in one big offers.csv -> now one file per week, so an old week is never touched again
#   - only the newest flyer was read, a missed week stayed missing -> now every week that is not done yet is made
#   - the work files are only needed during the run -> the clean-up keeps just the weekly files and needs_review.csv
#     (KEEP_WORK_FILES = True keeps everything, for checking)

import os
import re
import sys
import glob
import shutil
import subprocess
import time

# the stages in order: (name, file)
STAGES = [
    ("ingest",     "pipeline/ingest.py"),       # download this week's flyers -> data/flyers/<store>   (once)
    ("preprocess", "pipeline/preprocess.py"),   # which weeks are new? then per week: pages -> pictures + manifest
    ("ocr",        "pipeline/ocr.py"),          # pages -> text pieces + boxes (+ thin lines for Netto)
    ("structure",  "pipeline/structure.py"),    # text -> offers (each store by its own look)
    ("validate",   "pipeline/validate.py"),     # clean + check
    ("verify",     "pipeline/verify.py"),       # deep verification: repair, sort out, set aside
    ("load",       "pipeline/load.py"),         # add every store to data/output/offers_<week>.csv
    ("evaluate",   "pipeline/evaluate.py"),     # quality report -> logs/quality_report.txt
]

# clean-up at the end of a run: only these files are kept
KEEP_WORK_FILES = False                       # True = keep ALL work files (e.g. when Claude asks for page_N.csv)
KEEP_IN_OUTPUT = r"offers_\d{4}-W\d\d\.csv"   # data/output: the final file of every week (offers_2026-W46.csv)
KEEP_IN_REVIEW = ["needs_review.csv"]         # data/review/<store>: the offers you should look at
WORK_FOLDERS = ["data/pages", "data/text", "data/offers"]     # made again by every run
WEEKS_FILE = "data/weeks_to_do.txt"           # preprocess.py plan writes the new weeks here
REPORT_FILE = "logs/quality_report.txt"       # evaluate.py adds the report of every week of this run


def run_stage(name, command):
    """run one stage (same as typing: python pipeline/....py) -> stops the whole run if it fails"""
    print("\n========== Stage:", name, "==========")
    stage_start = time.time()
    result = subprocess.run([sys.executable] + command)
    seconds = round(time.time() - stage_start, 1)
    if result.returncode != 0 and name == "ingest":
        # a failed download does not stop the run: it goes on with the flyers you already have
        print("WARNING: not every download worked (see SUMMARY above) - going on with the flyers you have")
    elif result.returncode != 0:                         # 0 = everything fine, anything else = error
        print("\nSTOPPED: stage", name, "failed after", seconds, "seconds.")
        print("Fix the error above, then continue with:  python run.py", name)
        sys.exit(1)                                      # (no clean-up: the work files stay for the restart)
    print("---", name, "finished in", seconds, "seconds")


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
if names.index(start) > names.index("preprocess") and not os.path.exists("data/pages"):
    print("The work files of the last run were deleted by the clean-up - run everything: python run.py")
    sys.exit(1)

total_start = time.time()

# 2. download (once)
if start == "ingest":
    run_stage("ingest", ["pipeline/ingest.py"])
else:
    print("skip ingest (using the flyers you have)")

# 3. which weeks are new? (a week that is already in data/output is not run again)
if names.index(start) <= names.index("preprocess"):
    run_stage("preprocess (plan)", ["pipeline/preprocess.py", "plan"])
    with open(WEEKS_FILE, encoding="utf-8") as file:
        weeks = file.read().split()
    first_stage = "preprocess"
    if os.path.exists(REPORT_FILE):
        os.remove(REPORT_FILE)                       # a new report for this run
else:
    with open("data/current_week.txt", encoding="utf-8") as file:
        weeks = [file.read().strip()]                # a restart: only the week of the last run
    first_stage = start
if len(weeks) == 0:
    print("\nNothing new: every flyer week is already in data/output - nothing to do.")

# 4. every new week, oldest first: preprocess -> ocr -> structure -> validate -> verify -> load -> evaluate
for week in weeks:
    print("\n##################################  WEEK", week, " ##################################")
    for name, file in STAGES[names.index(first_stage):]:
        if name == "preprocess":
            run_stage(name, [file, week])            # preprocess.py 2026-W47 -> the pictures of week 47
        else:
            run_stage(name, [file])                  # the other stages work on that week (data/current_week.txt)
    first_stage = "preprocess"                       # (a restart only skips stages in its first week)

# 5. clean-up: delete the work files, keep only the weekly files and the offers to check
if KEEP_WORK_FILES:
    print("\nClean-up: skipped (KEEP_WORK_FILES = True) - all work files are kept")
else:
    try:
        for folder in WORK_FOLDERS:
            if os.path.exists(folder):
                shutil.rmtree(folder)
        if os.path.isdir("data/output"):                          # keep the weekly files, delete the rest
            for file_name in os.listdir("data/output"):           # (folders like data/output/old are not touched)
                if not re.fullmatch(KEEP_IN_OUTPUT, file_name) and os.path.isfile("data/output/" + file_name):
                    os.remove("data/output/" + file_name)
        for review_folder in glob.glob("data/review/*"):          # data/review/kaufland, data/review/netto, ...
            if not os.path.isdir(review_folder):
                continue
            for file_name in os.listdir(review_folder):
                if file_name not in KEEP_IN_REVIEW and os.path.isfile(review_folder + "/" + file_name):
                    os.remove(review_folder + "/" + file_name)
        print("\nClean-up: done. Kept the weekly files data/output/offers_<week>.csv and the needs_review.csv of every store")
    except PermissionError as error:
        print("\nClean-up: could not delete", error.filename, "- is it open (e.g. in Excel)? Close it, the next run cleans up.")

print("\nAll done in", round(time.time() - total_start, 1), "seconds.",
      "Weeks made in this run:", ", ".join(weeks) if weeks else "none (nothing new)")
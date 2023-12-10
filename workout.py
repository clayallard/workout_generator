import os
import random
import argparse
import pandas as pd
import numpy as np
from datetime import datetime
from datetime import date
from datetime import timedelta
import json
from collections import Counter
from urllib.request import urlopen


# This is my workout generator. I have a bi-weekly workout schedule where in the 14 days, I get 4 off days,
# 4 gym days, 4 cardio days, and 2 days of both gym and cardio. However, I cannot have 3 days in a row without
# cardio, 3 days in a row without gym, or 3 days in a row of rest. Every 4 months, the pattern is regenerated.
class Workout:

    # day will be today if it is the morning and tomorrow if it is the next day
    def __init__(self, work_type, specifics,
                 day=date.today() if datetime.now().strftime("%H") < "12" else date.today() + timedelta(1)):
        self.details = work_type
        self.specs = specifics
        self.day = day
        self.workout = ""

    def __run_case__(self, details=[]):
        if "run" in details:
            run = np.random.choice(["Very very very long distance run", "Very very long distance run",
                                    "Very long distance run", "Long distance run",
                                    "Intermediate distance sprints", "Short distance sprints"],
                                   p=[.01, .01, .03, .75, .1, .1])
            # endurance = np.random.choice(["Endurance", "Intermediate", "Short spurts"], p=[.75, .15, .1])
            run += " or " + np.random.choice(
                ["Treadmill", "Bike", "Stairmaster", "Row", "Ski machine", "Jacob's Ladder"],
                p=[.35, .3, .1, .08, .07, .1]) + " if weather is unsuitable\n"
            return run
        return self.__machine__() + "\n"

    def __machine__(self):
        endurance = np.random.choice(["Long long endurance", "long endurance", "Endurance", "Intermediate", "Short spurts"], p=[.01, .02, .57, .2, .2])
        return endurance + " " + np.random.choice(
            ["Treadmill", "Bike", "Stairmaster", "Row", "Ski machine", "Jacob's Ladder"],
            p=[.2, .3, .1, .15, .1, .15])

    def __reps__(self, lift):
        if "Dumbbell" in lift:
            return np.random.choice([5, 10, 15, 20, np.random.randint(1, 21)])
        return np.random.choice([1, 5, 10, 15, np.random.randint(1, 16)])

    def __gym_case__(self, details):
        routine = ""
        ab = False
        if np.random.random() < .25:
            routine += "Hold plank as long as possible\n"
        if np.random.random() < .25:
            routine += "Hang pull ups\n"
        if "abs" in details:
            routine += "Ab workout\n"
        if "cf" in details:
            routine += self.__cf__() + "\n"
        if "weights" in details:
            # if we have an ab workout or plank, we will have either cf or weights
            optional = ""
            func = self.__weights__
            if routine != "":
                optional = " (if time persists)"
                func = np.random.choice([self.__weights__, self.__cf__, self.__machine__, self.__run_case__],
                                        p=np.array([.7, .1, .1, .1]))
            return routine + func() + optional + "\n"
        return routine

    def __weights__(self):
        with open("Lifts.txt", "r") as f:
            lift_options = f.read().splitlines()
        lifts_dist = Counter(lift_options)
        freq = np.array(list(lifts_dist.values()))
        lifts = np.random.choice(list(lifts_dist), 2, replace=False, p=freq / sum(freq))
        l1 = lifts[0] + " for max set of " + str(self.__reps__(lifts[0])) + " reps"
        l2 = "\n" + lifts[1] + " for max set of " + str(
            self.__reps__(lifts[1])) + " reps" if np.random.random() > 0.1 else ""
        return l1 + l2

    def __cf__(self):
        if np.random.random() < .5:
            return "Quinn's workout"
        dow = self.day.weekday()
        cf_days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        rand_day = np.random.randint(0, 7)
        cf_day = self.day - timedelta(days=(dow - rand_day) % 7)
        return cf_days_of_week[rand_day] + " " + str(cf_day) + " Crossfit Workout"

        cf_days_of_week = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        ref_date = date(2023, 5, 28)
        # 0 % 4 is a rest day
        day_in_cycle = ((self.day - ref_date).days + 1) % 4
        choice = np.random.choice([i for i in range(4) if i != day_in_cycle])
        cf_day = self.day - timedelta(int(choice))
        dow = cf_day.weekday()
        return f"{cf_days_of_week[dow]} {cf_day} Crossfit Workout"

    def __warm_up__(self):
        return "Coming soon"

    def __workout_type_configurator__(self):
        specifics = self.specs
        self.workout = "Workout for " + str(self.day) + ":\n\n"
        morning_night = np.random.choice(["50 Push ups", "50 Sit ups", "50 Squats", "Break"], size=2)
        self.workout += morning_night[0] + "\n\n"
        if self.details == "run":
            self.workout += self.__run_case__(specifics)
        elif self.details == "gym":
            self.workout += self.__gym_case__(specifics)
        elif self.details == "off":
            self.workout += "Off Day\n"
        elif self.details == "run/gym":
            self.workout += self.__run_case__(specifics) + "\n" + self.__gym_case__(specifics)
        elif self.details == "gym/run":
            self.workout += self.__gym_case__(specifics) + "\n" + self.__run_case__(specifics)
        else:
            raise Exception("Invalid workout type")
        self.workout += "\n" + morning_night[1]

    def workout_of_day(self):
        if self.workout == "":
            self.__workout_type_configurator__()
        return self.workout


# def init_json():
#     init_file = {"structure": {"2023-2": {0: {"type": "gym/run", "details": ["cf", "run"]},
#                                           1: {"type": "off", "details": []},
#                                           2: {"type": "gym", "details": ["plank", "weights"]},
#                                           3: {"type": "run", "details": ["run"]},
#                                           4: {"type": "off", "details": []},
#                                           5: {"type": "gym", "details": ["weights"]},
#                                           6: {"type": "run", "details": ["run"]},
#                                           7: {"type": "run/gym", "details": ["machine", "abs", "weights"]},
#                                           8: {"type": "off", "details": []},
#                                           9: {"type": "gym", "details": ["weights"]},
#                                           10: {"type": "run", "details": ["run"]},
#                                           11: {"type": "off", "details": []},
#                                           12: {"type": "gym", "details": ["cf"]},
#                                           13: {"type": "run", "details": ["run"]},
#                                           }},
#                  "last_save": str(date.today())}
#     with open("details.json", "w") as f:
#         json.dump(init_file, f)
#
#     first_workout = "Workout for 2023-07-30:\n\nBike\n\nAb workout\nDumbbell Bench for max set of 10 reps\nDeadlift " \
#                     "for max set of 8 reps (if time persists) "
#
#     # workout data
#     df = pd.DataFrame({"Date": [str(date.today())], "Type": ["run/gym"], "Details": [["abs", "weights", "machine"]],
#                        "Workout": [first_workout]})
#     df.set_index("Date", inplace=True)
#     df.to_csv("workout_history.csv")


def workout_structure_generator():
    def condition(combo):
        streak_run = streak_lift = streak_rest = no_run = no_lift = 0
        for w in combo + combo[:3]:
            no_run += 1
            no_lift += 1
            # off case
            if w == "off":
                streak_rest += 1
                streak_run = streak_lift = 0
                # make sure none of the rules are broken
                if streak_rest >= 3 or max(no_run, no_lift) >= 3:
                    return False
                continue
            # one or the other (or both) will be incremented
            streak_rest = 0
            streak_run += 1
            streak_lift += 1

            # run case
            if "run" not in w:
                streak_run = 0
            else:
                no_run = 0

            # gym case
            if "gym" not in w:
                streak_lift = 0
            else:
                no_lift = 0
            # last check to make sure no rules are broken
            if max(streak_lift, streak_run, streak_rest, no_lift, no_run) >= 3:
                return False
        return True

    if np.random.random() < 1:
        # weekly schedule
        def create_week():
            workout_types = [t for t in ["run", "gym", "off"] for _ in range(2)] + ["both"]
            run_gym = ["run/gym", "gym/run"]
            np.random.shuffle(run_gym)
            np.random.shuffle(workout_types)
            workout_sched = workout_types * 2
            # get index of "both"
            idx = workout_sched.index("both")
            workout_sched[idx] = run_gym[0]
            workout_sched[idx + 7] = run_gym[1]
            return workout_sched

        workout_types = create_week()
        while not condition(workout_types):
            workout_types = create_week()
    else:
        # biweekly schedule
        workout_types = [t for t in ["run", "gym", "off"] for _ in range(4)] + ["run/gym", "gym/run"]
        np.random.shuffle(workout_types)
        while not condition(workout_types):
            np.random.shuffle(workout_types)

    gym_days = [str(g) for g in range(len(workout_types)) if "gym" in workout_types[g]]
    np.random.shuffle(gym_days)
    # cf_days = gym_days[0:2]
    # lift_days = gym_days[2:4]
    # plank_day = gym_days[4]
    # abs_day = gym_days[5]
    run_days = [str(r) for r in range(len(workout_types)) if "run" in workout_types[r]]
    np.random.shuffle(gym_days)
    details = {}
    for i in range(len(workout_types)):
        details[str(i)] = {"type": workout_types[i], "details": []}
    # inputting the specific kind of workouts
    details[gym_days[4]]["details"] += ["abs"]
    # details[gym_days[5]]["details"] += ["abs"]
    details[run_days[0]]["details"] += ["machine"]
    for i in range(2):
        details[gym_days[i]]["details"] += ["cf"]
    for i in range(2, 6):
        details[gym_days[i]]["details"] += ["weights"]
    for i in range(1, 6):
        details[run_days[i]]["details"] += ["run"]
    return details


def __get_version__(day):
    return day.strftime("%Y") + "-" + str(int((int(day.strftime("%m")) - 1) / 4) + 1)


def create_workout(day, details, df):
    ref_date = date(year=2023, month=5, day=28)
    cycle = (day - ref_date).days % 14
    if day.strftime("%m%d") in ["0101", "0501", "0901"]:
        details["structure"][__get_version__(day)] = workout_structure_generator()
    typ = details["structure"][__get_version__(day)][str(cycle)]["type"]
    dets = details["structure"][__get_version__(day)][str(cycle)]["details"]
    w = Workout(typ, dets, day)
    w.workout_of_day()
    date_format = day.strftime("%Y-%m-%d")
    df.loc[date_format] = [typ, dets, w.workout]


def output(details, df):
    details["last_save"] = str(max(df.index))
    df.sort_index(ascending=False, inplace=True)
    df.to_csv("workout_history.csv")
    with open("details.json", "w") as f:
        json.dump(details, f)


def workout_structure(details, day):
    version = __get_version__(day)
    struc = details["structure"][version]
    days_of_week = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    for s in range(len(struc)):
        if s > 0 and s % len(days_of_week) == 0:
            print()
        dow = days_of_week[s % len(days_of_week)]
        cycle = int(s / len(days_of_week) + 1)
        typ = struc[str(s)]["type"]
        detas = struc[str(s)]["details"]
        event = ", ".join(detas)
        print(f"{dow} {cycle}: {typ} -> {event}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--date",
                        default=date.today() if datetime.now().strftime("%H") < "12" else date.today() + timedelta(1),
                        type=lambda s: datetime.strptime(s, '%Y-%m-%d').date(),
                        help="Generate workouts up to this date and output this day's workout. Must be in "
                             "YYYY-MM-DD format")
    parser.add_argument("-r", "--reset", default=False,
                        help="If this is true, a new workout will be generated and overwritten over the "
                             "single existing workout", action="store_true")
    parser.add_argument("-a", "--reset_all", default=False,
                        help="If this is true, a new workout will be generated and overwritten for each "
                             "existing workout up to that date", action="store_true")
    parser.add_argument("-c", "--clear", default=False,
                        help="clears everything past a specified date", action="store_true")
    parser.add_argument("-t", "--tomorrow", default=False,
                        help="Get tomorrow's workout. This has priority over the date argument", action="store_true")
    parser.add_argument("-td", "--today", default=False,
                        help="Get tomorrow's workout. This has priority over the date argument", action="store_true")
    parser.add_argument("-s", "--structure", default=False,
                        help="Get workout structure for specified date", action="store_true")
    args = parser.parse_args()
    day = date.today() + timedelta(1) if args.tomorrow and not args.today else args.date
    day = date.today() if args.today else day
    reset_all = args.reset_all
    clear = args.clear
    structure = args.structure
    # reset_all takes precedence
    reset = True if reset_all else args.reset
    # import data
    with open("details.json", "r") as f:
        details = json.load(f)
    df = pd.read_csv("workout_history.csv", index_col="Date")

    start = datetime.strptime(details["last_save"], "%Y-%m-%d").date()
    # If it is a previous day, just return that day's workout
    if structure:
        try:
            workout_structure(details, day)
        except:
            print("No version exists for this date")
        return
    if clear:
        df = df.loc[str(day) >= df.index]
        recent_ver = __get_version__(datetime.strptime(max(df.index), "%Y-%m-%d").date())
        sorted_versions = sorted(details["structure"].keys())
        ind_of = sorted_versions.index(recent_ver)
        delete = sorted_versions[ind_of + 1:]
        for d in delete:
            details["structure"].pop(d)
            print("Version " + d + " has been removed.")
        print("All workouts beyond the day " + str(day) + " have been removed")
    elif day <= start:
        if not reset:
            if str(day) in df.index:
                print(df.loc[str(day)]["Workout"])
            else:
                print("No recorded workout for this day")
            output(details, df)
            return
        elif reset_all:
            day_count = (start - day).days + 1
            for single_date in (day + timedelta(n) for n in range(day_count)):
                create_workout(single_date, details, df)
        else:
            create_workout(day, details, df)
    else:
        day_count = (day - start).days
        for single_date in (start + timedelta(n + 1) for n in range(day_count)):
            create_workout(single_date, details, df)

    print(df.loc[str(day)]["Workout"])

    output(details, df)

    # w = Workout("run/gym", ["abs", "weights", "machine"])
    # print(w.workout_of_day())
    # init_json()


if __name__ == "__main__":
    main()

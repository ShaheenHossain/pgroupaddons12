# -*- coding: utf-8 -*-

from eagle.fields import datetime
from datetime import timedelta


def eagle_get_date(eagle_date_filter_selection):
    series = eagle_date_filter_selection
    return eval("eagle_date_series_"+series.split("_")[0])(series.split("_")[1])


# Last Specific Days Ranges : 7, 30, 90, 365
def eagle_date_series_l(eagle_date_selection):
    eagle_date_data = {}
    date_filter_options = {
        'day': 0,
        'week': 7,
        'month': 30,
        'quarter': 90,
        'year': 365,
    }
    eagle_date_data["selected_end_date"] = datetime.strptime(datetime.now().strftime("%Y-%m-%d 23:59:59"),'%Y-%m-%d %H:%M:%S')
    eagle_date_data["selected_start_date"] = datetime.strptime((datetime.now() - timedelta(
        days=date_filter_options[eagle_date_selection])).strftime("%Y-%m-%d 00:00:00"),'%Y-%m-%d %H:%M:%S')
    return eagle_date_data


# Current Date Ranges : Week, Month, Quarter, year
def eagle_date_series_t(eagle_date_selection):
    return eval("eagle_get_date_range_from_"+eagle_date_selection)("current")


# Previous Date Ranges : Week, Month, Quarter, year
def eagle_date_series_ls(eagle_date_selection):
    return eval("eagle_get_date_range_from_"+eagle_date_selection)("previous")


# Next Date Ranges : Day, Week, Month, Quarter, year
def eagle_date_series_n(eagle_date_selection):
    return eval("eagle_get_date_range_from_"+eagle_date_selection)("next")


def eagle_get_date_range_from_day(date_state):
    eagle_date_data = {}

    date = datetime.now()

    if date_state == "previous":
        date = date - timedelta(days=1)
    elif date_state == "next":
        date = date + timedelta(days=1)

    eagle_date_data["selected_start_date"] = datetime(date.year,date.month,date.day)
    eagle_date_data["selected_end_date"] = datetime(date.year, date.month, date.day) + timedelta(days=1, seconds=-1)
    return eagle_date_data


def eagle_get_date_range_from_week(date_state):
    eagle_date_data = {}

    date = datetime.now()

    if date_state == "previous":
        date = date - timedelta(days=7)
    elif date_state == "next":
        date = date + timedelta(days=7)

    date_iso = date.isocalendar()
    year = date_iso[0]
    week_no = date_iso[1]

    eagle_date_data["selected_start_date"] = datetime.strptime('%s-W%s-1'%(year,week_no-1), "%Y-W%W-%w")
    eagle_date_data["selected_end_date"] = eagle_date_data["selected_start_date"] + timedelta(days=6,hours=23,minutes=59,seconds=59,milliseconds=59)
    return eagle_date_data


def eagle_get_date_range_from_month(date_state):
    eagle_date_data = {}

    date = datetime.now()
    year = date.year
    month = date.month

    if date_state=="previous":
        month -= 1
        if month==0:
            month = 12
            year -= 1
    elif date_state == "next":
        month += 1
        if month==13:
            month = 1
            year += 1


    end_year = year
    end_month = month
    if month == 12:
        end_year +=1
        end_month = 1
    else:
        end_month +=1


    eagle_date_data["selected_start_date"] = datetime(year, month, 1)
    eagle_date_data["selected_end_date"] = datetime(end_year, end_month, 1)-timedelta(seconds=1)
    return eagle_date_data


def eagle_get_date_range_from_quarter(date_state):
    eagle_date_data = {}

    date = datetime.now()
    year = date.year
    quarter = int((date.month - 1) / 3) + 1

    if date_state == "previous":
        quarter -= 1
        if quarter == 0:
            quarter = 4
            year -= 1
    elif date_state == "next":
        quarter += 1
        if quarter == 5:
            quarter = 1
            year += 1

    eagle_date_data["selected_start_date"] = datetime(year, 3 * quarter - 2, 1)

    month = 3 * quarter
    remaining = int(month / 12)
    eagle_date_data["selected_end_date"] = datetime(year + remaining, month % 12 + 1, 1)-timedelta(seconds=1)

    return eagle_date_data


def eagle_get_date_range_from_year(date_state):
    eagle_date_data = {}

    date = datetime.now()
    year = date.year

    if date_state == "previous":
        year -= 1
    elif date_state == "next":
        year += 1

    eagle_date_data["selected_start_date"] = datetime(year, 1, 1)
    eagle_date_data["selected_end_date"] = datetime(year+1, 1, 1)-timedelta(seconds=1)

    return eagle_date_data


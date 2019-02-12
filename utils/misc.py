import pytz
import datetime as dt

def possible_timezones(tz_offset, common_only=True):
    # pick one of the timezone collections
    timezones = pytz.common_timezones if common_only else pytz.all_timezones

    # convert the float hours offset to a timedelta
    offset_days, offset_seconds = 0, int(tz_offset * 3600)
    if offset_seconds < 0:
        offset_days = -1
        offset_seconds += 24 * 3600
    desired_delta = dt.timedelta(offset_days, offset_seconds)

    # Loop through the timezones and find any with matching offsets
    null_delta = dt.timedelta(0, 0)
    results = []
    for tz_name in timezones:
        tz = pytz.timezone(tz_name)
        non_dst_offset = getattr(tz, '_transition_info', [[null_delta]])[-1]
        if desired_delta == non_dst_offset[0]:
            results.append(tz_name)

    return results
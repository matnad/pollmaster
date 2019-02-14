import argparse

import pytz
import datetime as dt


class CustomFormatter(argparse.RawTextHelpFormatter):
    def _format_action_invocation(self, action):
        if not action.option_strings:
            metavar, = self._metavar_formatter(action, action.dest)(1)
            return metavar
        else:
            parts = []
            # if the Optional doesn't take a value, format is:
            #    -s, --long
            if action.nargs == 0:
                parts.extend(action.option_strings)

            # if the Optional takes a value, format is:
            #    -s ARGS, --long ARGS
            # change to
            #    -s, --long ARGS
            else:
                default = action.dest.upper()
                args_string = self._format_args(action, default)
                for option_string in action.option_strings:
                    # parts.append('%s %s' % (option_string, args_string))
                    parts.append('%s' % option_string)
                parts[-1] += ' %s' % args_string
            return ', '.join(parts)


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
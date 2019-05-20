# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata import config
import os


class ConfigEnv(config.Config):
    def get(self, section, option, default=None, type=str):
        res = os.environ.get('LIBMOZDATA_CFG_' + section.upper() + '_' + option.upper())
        if not res:
            return default
        if type == list or type == set:
            return type([s.strip(' /t') for s in res.split(',')])
        return type(res)


config.set_config(ConfigEnv())

from bisect import bisect_left as bisect
import copy
import datetime
import dateutil.parser
import libmozdata.utils as lmdutils
from libmozdata.bugzilla import Bugzilla
from libmozdata.connection import Connection
from math import ceil
import pytz


MIMES = {
    'text/x-phabricator-request',
    'text/x-github-pull-request',
    'text/x-review-board-request',
}
Connection.CHUNK_SIZE = 128
M3_START_DATE = '2019-05-01'
M3_END_DATE = '2019-06-07'


def get_date(s):
    return dateutil.parser.parse(s).replace(tzinfo=pytz.utc)


def get_prev_monday(d):
    return d + datetime.timedelta(days=-d.weekday())


def get_params():
    params = {
        'include_fields': [
            'creation_time',
            'component',
            'cf_fission_milestone',
            'status',
            'resolution',
            'priority',
            'assigned_to',
            'summary',
            'id',
        ],
        'f1': 'cf_fission_milestone',
        'o1': 'notequals',
        'v1': '---',
    }
    return params


def get_bugs():
    def bug_handler(bug, data):
        del bug['assigned_to_detail']
        if not bug['resolution']:
            bug['resolution'] = '---'
        data.append(bug)

    params = get_params()
    bugs = []

    Bugzilla(
        params, bughandler=bug_handler, bugdata=bugs, timeout=600
    ).get_data().wait()

    return bugs


def get_milestone_extra_info(bugs, M):
    def attachment_handler(attachments, bugid, data):
        for attachment in attachments:
            if attachment['is_obsolete'] == 0 and attachment['content_type'] in MIMES:
                data[int(bugid)]['patch'] = True
                break

    def history_handler(bug, data):
        bugid = bug['id']
        d = data[bugid]
        for h in bug['history']:
            for c in h['changes']:
                if c.get('field_name') == 'status':
                    if c.get('added') == 'RESOLVED':
                        d['dates'].append(get_date(h['when']))
                        d['states'].append(True)
                    elif (
                        c.get('removed') == 'RESOLVED' and c.get('added') != 'VERIFIED'
                    ):
                        d['dates'].append(get_date(h['when']))
                        d['states'].append(False)

    data = {}
    for bug in bugs:
        if bug['cf_fission_milestone'] != M:
            continue
        data[bug['id']] = {
            'dates': [get_date(bug['creation_time'])],
            'states': [False],
            'patch': False,
        }

    Bugzilla(
        bugids=list(data.keys()),
        attachmenthandler=attachment_handler,
        attachmentdata=data,
        attachment_include_fields=['bug_id', 'is_obsolete', 'content_type'],
        historyhandler=history_handler,
        historydata=data,
    ).get_data().wait()

    return data


def is_dom(comp):
    return comp.startswith('DOM: ') or comp == 'Document Navigation'


def mk_weeks(start, end):
    start = lmdutils.get_date_ymd(start)
    start = get_prev_monday(start)
    end = lmdutils.get_date_ymd(end)
    weeks = []
    while start < end:
        weeks.append(
            {
                'start': start,
                'end': min(start + datetime.timedelta(days=6), end),
                'resolved': 0,
                'unresolved': 0,
            }
        )
        start += datetime.timedelta(days=7)

    return weeks


def state_for_week(start, end, info):
    dates = info['dates']
    states = info['states']
    i = bisect(dates, end)
    if i == len(dates):
        return states[i - 1]

    if dates[i] == end:
        return states[i]

    if i == 0:
        return None

    return states[i - 1]


def mk_weeks_stats(weeks, data):
    for info in data.values():
        for week in weeks:
            x = state_for_week(week['start'], week['end'], info)
            if x is not None:
                if x:
                    week['resolved'] += 1
                else:
                    week['unresolved'] += 1


def mk_burndown(start, end, data):
    weeks = mk_weeks(start, end)
    periods = len(weeks)
    mk_weeks_stats(weeks, data)
    tomorrow = lmdutils.get_date_ymd('tomorrow')
    labels = []
    totals = []
    _totals = []
    unresolved = []
    forecasted = []
    todo = None
    for n, week in enumerate(weeks):
        date = week['end'].strftime('%m-%d')
        labels.append(date)
        total = week['resolved'] + week['unresolved']
        _totals.append(total)
        if week['start'] < tomorrow:
            totals.append(total)
            unresolved.append(week['unresolved'])
        else:
            totals.append(None)
            unresolved.append(None)

        # diff from the prev week
        diff = 0 if len(_totals) == 1 else _totals[-1] - _totals[-2]
        last = total if len(forecasted) == 0 else forecasted[-1] + diff
        if diff != 0:
            # we need to readjust because new bugs appeared
            todo = ceil(last / (periods - n))
        if todo is None:
            todo = ceil(total / periods)
        forecasted.append(max(0, last - todo))

    return {
        'labels': labels,
        'totals': totals,
        'unresolved': unresolved,
        'forecasted': forecasted,
        'unresolved_link': 'https://bugzilla.mozilla.org/buglist.cgi?list_id=14664631&o1=equals&v1=M3&f1=cf_fission_milestone&bug_status=UNCONFIRMED&bug_status=NEW&bug_status=ASSIGNED&bug_status=REOPENED',
        'total_link': 'https://bugzilla.mozilla.org/buglist.cgi?o1=equals&v1=M3&f1=cf_fission_milestone&list_id=14664661',
    }


def mk_table(data):
    header = [
        'Priority',
        'Summary',
        'Resolution',
        'Assignee',
        'Bug Number',
        'Fission Milestone',
        'Status',
    ]
    header_map = [
        'priority',
        'summary',
        'resolution',
        'assigned_to',
        'id',
        'cf_fission_milestone',
        'status',
    ]

    _data = sorted(data, key=lambda p: -p['id'])
    data = [[x[f] for f in header_map] for x in _data]
    data = {'header': header, 'data': data}

    return data


def mk_doughnut(data):
    data = sorted(data.items())
    labels = [k for k, _ in data]
    data = [v for _, v in data]

    return {'labels': labels, 'data': data, 'links': []}


def get_stats(bugs):
    extra_m3 = get_milestone_extra_info(bugs, 'M3')
    extra_m2 = get_milestone_extra_info(bugs, 'M2')
    burndown_m3 = mk_burndown(M3_START_DATE, M3_END_DATE, extra_m3)
    total_milestones = len(bugs)
    milestones = {'M1': [], 'M2': [], 'M3': [], 'M4': [], '?': [], 'Future': []}
    milestones_stats = {k: 0 for k in milestones.keys()}
    status = {}
    status_m3 = {
        'labels': ['Open without patches', 'Open with patches', 'Resolved'],
        'data': [0, 0, 0],
        'links': [[], [], []],
    }
    status_m2 = copy.deepcopy(status_m3)
    status_infos = {'M2': status_m2, 'M3': status_m3}
    extras = {'M2': extra_m2, 'M3': extra_m3}

    for bug in bugs:
        m = bug['cf_fission_milestone']
        milestones[m].append(bug)
        milestones_stats[m] += 1

        s = bug['status']
        status[s] = status.get(s, 0) + 1

        if m in status_infos:
            info = status_infos[m]
            if s in {'NEW', 'ASSIGNED', 'REOPENED'}:
                if extras[m][bug['id']]['patch']:
                    info['links'][1].append(str(bug['id']))
                    info['data'][1] += 1
                else:
                    info['links'][0].append(str(bug['id']))
                    info['data'][0] += 1
            else:
                info['links'][2].append(str(bug['id']))
                info['data'][2] += 1

    for m, data in milestones.items():
        if m != 'M1':
            milestones[m] = mk_table(data)

    for info in status_infos.values():
        for i, bugids in enumerate(info['links']):
            info['links'][
                i
            ] = 'https://bugzilla.mozilla.org/buglist.cgi?bug_id=' + ','.join(bugids)

    return {
        'stats': {
            'status': mk_doughnut(status),
            'statusM3': status_m3,
            'statusM2': status_m2,
            'milestones': mk_doughnut(milestones_stats),
            'totalMilestones': total_milestones,
            'burndown': burndown_m3,
        },
        'tables': {'milestones': milestones},
    }

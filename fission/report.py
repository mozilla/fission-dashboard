# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from libmozdata.bugzilla import Bugzilla


MIMES = {
    'text/x-phabricator-request',
    'text/x-github-pull-request',
    'text/x-review-board-request',
}


def get_params():
    params = {
        'include_fields': [
            'triage_owner',
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
        del bug['triage_owner_detail']
        if not bug['resolution']:
            bug['resolution'] = '---'
        data.append(bug)

    params = get_params()
    bugs = []

    Bugzilla(
        params, bughandler=bug_handler, bugdata=bugs, timeout=600
    ).get_data().wait()

    return bugs


def get_bugs_with_patch(bugids):
    def attachment_handler(attachments, bugid, data):
        for attachment in attachments:
            if attachment['is_obsolete'] == 0 and attachment['content_type'] in MIMES:
                data.add(int(bugid))
                break

    data = set()

    Bugzilla(
        bugids=bugids,
        attachmenthandler=attachment_handler,
        attachmentdata=data,
        attachment_include_fields=['bug_id', 'is_obsolete', 'content_type'],
    ).get_data().wait()

    return data


def is_dom(comp):
    return comp.startswith('DOM: ') or comp == 'Document Navigation'


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

    return {'labels': labels, 'data': data}


def get_stats(bugs):
    m2 = [bug['id'] for bug in bugs if bug['cf_fission_milestone'] == 'M2']
    m2_patch = get_bugs_with_patch(m2)

    total_milestones = len(bugs)
    milestones = {'M1': [], 'M2': [], 'M3': [], '?': [], 'Future': []}
    milestones_stats = {k: 0 for k in milestones.keys()}
    status = {}
    status_m2 = {}
    dom = {}

    for bug in bugs:
        m = bug['cf_fission_milestone']
        milestones[m].append(bug)
        milestones_stats[m] += 1

        s = bug['status']
        status[s] = status.get(s, 0) + 1

        if m == 'M2' and s in {'NEW', 'ASSIGNED', 'RESOLVED'}:
            if bug['id'] in m2_patch:
                s += ' with patch'
            status_m2[s] = status_m2.get(s, 0) + 1

        c = bug['component']
        if is_dom(c):
            dom[c] = dom.get(c, 0) + 1

    for m, data in milestones.items():
        milestones[m] = mk_table(data)

    return {
        'stats': {
            'status': mk_doughnut(status),
            'statusM2': mk_doughnut(status_m2),
            'dom': mk_doughnut(dom),
            'milestones': mk_doughnut(milestones_stats),
            'totalMilestones': total_milestones,
        },
        'tables': {'milestones': milestones},
    }

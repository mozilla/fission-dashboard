# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from flask import Flask, jsonify, send_from_directory
from . import cache


app = Flask(__name__, template_folder='../templates', static_folder='../static')


@app.route('/')
def default():
    return send_from_directory(app.static_folder, 'report.html')


@app.route('/data')
def data():
    return jsonify(cache.get_data())


@app.route('/<path:filename>')
def something(filename):
    return send_from_directory(app.static_folder, filename)

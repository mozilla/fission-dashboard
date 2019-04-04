# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

from flask import Flask, jsonify, send_from_directory
import flask
from flask_cors import CORS
import httplib2
from oauth2client import client, clientsecrets
import os

from . import cache


app = Flask(__name__, static_folder='../static')
cors = CORS(app)
app.config['CORS_HEADERS'] = 'Content-Type'
app.secret_key = os.environ.get('SESSION_KEY')


@app.after_request
def add_header(r):
    r.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    r.headers["Pragma"] = "no-cache"
    return r


def check_credentials():
    if not os.environ.get('CLIENT_SECRETS'):
        return

    if 'credentials' not in flask.session:
        return flask.redirect(flask.url_for('oauth2callback'))

    credentials = flask.session['credentials']
    credentials = client.OAuth2Credentials.from_json(credentials)
    if credentials.access_token_expired:
        return flask.redirect(flask.url_for('oauth2callback'))


@app.route('/logout')
def logout():
    # Delete the user's profile and the credentials stored by oauth2.
    credentials = flask.session.pop('credentials', None)
    if credentials:
        credentials = client.OAuth2Credentials.from_json(credentials)
        try:
            credentials.revoke(httplib2.Http())
        except client.TokenRevokeError:
            pass
        flask.session.modified = True

    return send_from_directory(app.static_folder, 'logout.html')


@app.route('/oauth2callback')
def oauth2callback():
    # client_secrets.json is got from https://console.developers.google.com

    class AuthCache(object):
        def get(self, filename, namespace=''):
            CSJ = 'client_secrets.json'
            OSNS = 'oauth2client:secrets#ns'
            if filename == CSJ and namespace == OSNS:
                c_secrets = os.environ.get('CLIENT_SECRETS', '')
                if c_secrets:
                    c_type, c_info = clientsecrets.loads(c_secrets)
                    return {c_type: c_info}
            return None

    flow = client.flow_from_clientsecrets(
        'client_secrets.json',
        scope='email',
        cache=AuthCache(),
        redirect_uri=flask.url_for('oauth2callback', _external=True),
    )

    if 'code' not in flask.request.args:
        auth_uri = flow.step1_get_authorize_url()
        return flask.redirect(auth_uri)

    auth_code = flask.request.args.get('code')
    credentials = flow.step2_exchange(auth_code)
    email = credentials.id_token['email']
    if email.endswith('mozilla.com'):
        flask.session['credentials'] = credentials.to_json()
        return flask.redirect(flask.url_for('default'))

    flask.abort(401)


@app.errorhandler(401)
def custom_401(error):
    return flask.Response(
        'You\'re not allowed to access to this page.',
        401,
        {'WWWAuthenticate': 'Basic realm="Login Required"'},
    )


@app.route('/')
def default():
    r = check_credentials()
    if r:
        return r
    return send_from_directory(app.static_folder, 'report.html')


@app.route('/data')
def data():
    if 'credentials' in flask.session:
        return jsonify(cache.get_data())

    r = check_credentials()
    if r:
        return r
    return jsonify(cache.get_data())


@app.route('/<path:filename>')
def something(filename):
    r = check_credentials()
    if r:
        return r
    return send_from_directory(app.static_folder, filename)

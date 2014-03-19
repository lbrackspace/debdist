#!/usr/bin/env python
# This file is part of DebDist.
#
# DebDist is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# DebDist is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with DebDist.  If not, see <http://www.gnu.org/licenses/>.

import ConfigParser
import os

import debian.debfile
import flask
import flask_wtf
import hashlib
import json
import OpenSSL
import requests
import wtforms


app = flask.Flask(__name__)


class DebForm(flask_wtf.Form):
    pass


class DebDistClient():
    def __init__(self):
        config = ConfigParser.SafeConfigParser()
        config.read("dev.cfg")
        self.deb_path = config.get('client', 'deb_path')
        self.deb_base_url = config.get('client', 'deb_base_url')
        self.server_url = config.get('client', 'remote_url')
        self.auth_token = config.get('auth', 'token')
        self.ssl_context = OpenSSL.SSL.Context(OpenSSL.SSL.SSLv23_METHOD)
        self.ssl_context.use_privatekey_file('server.key')
        self.ssl_context.use_certificate_file('server.crt')
        app.config.from_object('config')
        app.secret_key = self.auth_token


    def fill_form(self, debs):
        for deb in debs:
            control = debs[deb]
            name = ' - '.join((control['Package'], control['Version']))
            setattr(DebForm, deb, wtforms.BooleanField(label=name,
                                                       id=deb,
                                                       description=control[
                                                           'Description']))


    def get_debs(self):
        deb_files = [f for f in os.listdir(self.deb_path) if f.endswith(".deb")]
        deb_controls = {}
        for deb_name in deb_files:
            deb = debian.debfile.DebFile(os.path.join(self.deb_path, deb_name))
            deb_controls[deb_name] = deb.debcontrol()
        return deb_controls


    def send_debs(self, debs):
        headers = {'content-type': 'application/json',
                   'x-auth-token': self.auth_token}
        data = {'debs': []}
        for deb in debs:
            url = '/'.join((self.deb_base_url, deb.id))
            path = os.path.join(self.deb_path, deb.id)
            md5sum = hashlib.md5()
            f = open(path)
            while True:
                stuff = f.read(1024)
                if not stuff: break
                md5sum.update(stuff)
            data['debs'].append({'url': url, 'md5': md5sum.hexdigest()})
        r = requests.post(self.server_url, headers=headers,
                          data=json.dumps(data), verify=False)
        return r.status_code

    def run(self):
        app.run(debug=True, port=5444, ssl_context=self.ssl_context)
        print("Exiting...")


@app.route('/', methods=('GET', 'POST'))
def landing():
    debs = client.get_debs()
    client.fill_form(debs)
    form = DebForm()
    selected, status = None, None
    if form.validate_on_submit():
        selected = [x for x in form if x.data == True]
        status = client.send_debs(selected)
    return flask.render_template("index.html", debs=debs, form=form,
                                 selected=selected, status=status)


if __name__ == '__main__':
    client = DebDistClient()
    client.run()

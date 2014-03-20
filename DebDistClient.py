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

import collections
import ConfigParser
import gzip
import os
import re

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


    def fill_form(self, versions):
        for version in versions:
            attribute_name = version.replace(".","_")
            description=""
            for package in versions[version]:
                description += package['name'] + ", "
            description=description[0:-2]
            setattr(DebForm, attribute_name,
                    wtforms.BooleanField(label=version,
                                         description=description))

    def parse_release(self):
        release = os.path.join(self.deb_path, "Release")
        try:
            contents = file(release).read()
        except:
            contents = gzip.open(release).read()

        match = re.match(".* (.*Packages)\n", contents, flags=re.DOTALL).group(
            1)
        if match:
            return self.parse_packages(os.path.join(self.deb_path, match))
        raise Exception("No packages file found")

    def parse_packages(self, filename):
        if filename.endswith(".gz"):
            contents = gzip.open(filename).read()
        else:
            contents = file(filename).read()

        packages = re.findall(
            ".*?Package:[ ]?(.*?)\n"
            ".*?Version:[ ]?(.*?)\n"
            ".*?Filename:[ ]?(.*?)\n",
            contents, flags=re.DOTALL)

        versions = {}
        for p in packages:
            info = {"name": p[0], "file": p[2]}
            if p[1] not in versions:
                versions[p[1]] = []
            versions[p[1]].append(info)

        valid_versions = {}
        for v in versions:
            if re.match("^1\.[0-9]+\.[0-9]+$", v) and len(versions[v]) > 1:
                valid_versions[v] = versions[v]
        return valid_versions

    def send_debs(self, selected, versions):
        headers = {'content-type': 'application/json',
                   'x-auth-token': self.auth_token}
        data = {'debs': []}
        for vid in selected:
            version = versions[vid.name.replace("_",".")]
            for file in version:
                url = '/'.join((self.deb_base_url, file['file']))
                path = os.path.join(self.deb_path, file['file'])
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
    versions = client.parse_release()
    client.fill_form(versions)
    form = DebForm()
    selected, status = None, None
    if form.validate_on_submit():
        selected = [x for x in form if x.data == True]
        status = client.send_debs(selected, versions)
    return flask.render_template("index.html", versions=versions, form=form,
                                 selected=selected, status=status)


if __name__ == '__main__':
    client = DebDistClient()
    client.run()

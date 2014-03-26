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
import functools
import hashlib
import jinja2
import json
import OpenSSL
import requests
import wtforms


app = flask.Flask(__name__)


class DebForm(flask_wtf.Form):
    def init_lists(self):
        bools = [x for x in self if isinstance(x, DebBoolean)]
        for b in bools:
            versions = [x.strip() for x in b.description.split(",")]
            b.set_list(versions)


@functools.total_ordering
class DebBoolean(wtforms.BooleanField):
    list = []

    def set_list(self, list):
        self.list = list

    def __lt__(self, other):
        if "_" not in self.name or not isinstance(other, DebBoolean):
            return self
        my_names = self.name.split("_")
        other_names = other.name.split("_")

        my_value = 0
        other_value = 0
        for v in my_names:
            my_value = my_value * 1000 + int(v)

        for v in other_names:
            other_value = other_value * 1000 + int(v)

        return my_value < other_value


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
        app.jinja_env.filters['deb_sort'] = deb_sort


    def fill_form(self, versions):
        for version in versions:
            attribute_name = version.replace(".", "_")
            description = ""
            for package in versions[version]:
                filename = package['file']
                filename = filename[filename.rfind("/")+1:]
                description += filename + ", "
            description = description[0:-2]
            boolean = DebBoolean(label=version, description=description)
            setattr(DebForm, attribute_name, boolean)

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
            version = versions[vid.name.replace("_", ".")]
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


def deb_sort(iterable, show_version=None):
    if iterable is None or isinstance(iterable, jinja2.Undefined):
        return iterable
    if show_version:
        show_version = show_version.replace(".", "_")
        new_list = [x for x in iterable if
                    isinstance(x, DebBoolean) and x.name.startswith(
                        show_version)]
    else:
        new_list = [x for x in iterable if isinstance(x, DebBoolean)]
    new_list.sort(reverse=True)
    return new_list


@app.route('/', methods=('GET', 'POST'))
def landing():
    versions = client.parse_release()
    major_versions = set([x[0:4] for x in versions])
    client.fill_form(versions)
    show = flask.request.values['v'] if 'v' in flask.request.values else None
    form = DebForm()
    form.init_lists()
    selected, status = None, None
    if form.validate_on_submit():
        selected = [x for x in form if x.data == True]
        status = client.send_debs(selected, versions)
    return flask.render_template("base.html", major_versions=major_versions,
                                 form=form, selected=selected, status=status,
                                 show_version=show)


if __name__ == '__main__':
    client = DebDistClient()
    client.run()

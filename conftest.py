# -*- coding: utf-8 -*-
"""

    mslib.conftest
    ~~~~~~~~~~~~~~

    common definitions for py.test

    This file is part of MSS.

    :copyright: Copyright 2016-2017 Reimar Bauer
    :copyright: Copyright 2016-2023 by the MSS team, see AUTHORS.
    :license: APACHE-2.0, see LICENSE for details.

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.
"""

import importlib.util
import os
import sys
import mock
from PyQt5 import QtWidgets
# Disable pyc files
sys.dont_write_bytecode = True

import pytest
import fs
import shutil
import keyring
from mslib.mswms.demodata import DataFiles
import tests.constants as constants

# make a copy for mscolab test, so that we read different pathes during parallel tests.
sample_path = os.path.join(os.path.dirname(__file__), "tests", "data")
shutil.copy(os.path.join(sample_path, "example.ftml"), constants.ROOT_DIR)


class TestKeyring(keyring.backend.KeyringBackend):
    """A test keyring which always outputs the same password
    from Runtime Configuration
    https://pypi.org/project/keyring/#third-party-backends
    """
    priority = 1

    passwords = {}

    def reset(self):
        self.passwords = {}

    def set_password(self, servicename, username, password):
        self.passwords[servicename + username] = password

    def get_password(self, servicename, username):
        return self.passwords.get(servicename + username, "password from TestKeyring")

    def delete_password(self, servicename, username):
        if servicename + username in self.passwords:
            del self.passwords[servicename + username]


# set the keyring for keyring lib
keyring.set_keyring(TestKeyring())


@pytest.fixture(autouse=True)
def keyring_reset():
    keyring.get_keyring().reset()


def pytest_addoption(parser):
    parser.addoption("--msui_settings", action="store")


def pytest_generate_tests(metafunc):
    option_value = metafunc.config.option.msui_settings
    if option_value is not None:
        msui_settings_file_fs = fs.open_fs(constants.MSUI_CONFIG_PATH)
        msui_settings_file_fs.writetext("msui_settings.json", option_value)
        msui_settings_file_fs.close()


if os.getenv("TESTS_VISIBLE") == "TRUE":
    Display = None
else:
    try:
        from pyvirtualdisplay import Display
    except ImportError:
        Display = None

if not constants.SERVER_CONFIG_FS.exists(constants.SERVER_CONFIG_FILE):
    print('\n configure testdata')
    # ToDo check pytest tmpdir_factory
    examples = DataFiles(data_fs=constants.DATA_FS,
                         server_config_fs=constants.SERVER_CONFIG_FS)
    examples.create_server_config(detailed_information=True)
    examples.create_data()

if not constants.SERVER_CONFIG_FS.exists(constants.MSCOLAB_CONFIG_FILE):
    config_string = f'''
# SQLALCHEMY_DB_URI = 'mysql://user:pass@127.0.0.1/mscolab'
import os
import logging
import fs
import secrets
from urllib.parse import urljoin

ROOT_DIR = '{constants.ROOT_DIR}'
# directory where mss output files are stored
root_fs = fs.open_fs(ROOT_DIR)
if not root_fs.exists('colabTestData'):
    root_fs.makedir('colabTestData')
BASE_DIR = ROOT_DIR
DATA_DIR = fs.path.join(ROOT_DIR, 'colabTestData')
# mscolab data directory
MSCOLAB_DATA_DIR = fs.path.join(DATA_DIR, 'filedata')

# In the unit days when Operations get archived because not used
ARCHIVE_THRESHOLD = 30

# To enable logging set to True or pass a logger object to use.
SOCKETIO_LOGGER = True

# To enable Engine.IO logging set to True or pass a logger object to use.
ENGINEIO_LOGGER = True

# used to generate and parse tokens
SECRET_KEY = secrets.token_urlsafe(16)

# used to generate the password token
SECURITY_PASSWORD_SALT = secrets.token_urlsafe(16)

# looks for a given category for an operation ending with GROUP_POSTFIX
# e.g. category = Tex will look for TexGroup
# all users in that Group are set to the operations of that category
# having the roles in the TexGroup
GROUP_POSTFIX = "Group"

# mail settings
MAIL_SERVER = 'localhost'
MAIL_PORT = 25
MAIL_USE_TLS = False
MAIL_USE_SSL = True

# mail authentication
MAIL_USERNAME = os.environ.get('APP_MAIL_USERNAME')
MAIL_PASSWORD = os.environ.get('APP_MAIL_PASSWORD')

# mail accounts
MAIL_DEFAULT_SENDER = 'MSS@localhost'

# enable verification by Mail
MAIL_ENABLED = False

SQLALCHEMY_DB_URI = 'sqlite:///' + urljoin(DATA_DIR, 'mscolab.db')

# mscolab file upload settings
UPLOAD_FOLDER = fs.path.join(DATA_DIR, 'uploads')
MAX_UPLOAD_SIZE = 2 * 1024 * 1024  # 2MB

# text to be written in new mscolab based ftml files.
STUB_CODE = """<?xml version="1.0" encoding="utf-8"?>
<FlightTrack version="1.7.6">
  <ListOfWaypoints>
    <Waypoint flightlevel="250" lat="67.821" location="Kiruna" lon="20.336">
      <Comments></Comments>
    </Waypoint>
    <Waypoint flightlevel="250" lat="78.928" location="Ny-Alesund" lon="11.986">
      <Comments></Comments>
    </Waypoint>
  </ListOfWaypoints>
</FlightTrack>
"""
enable_basic_http_authentication = False

# enable login by identity provider
USE_SAML2 = False
'''
    ROOT_FS = fs.open_fs(constants.ROOT_DIR)
    if not ROOT_FS.exists('mscolab'):
        ROOT_FS.makedir('mscolab')
    with fs.open_fs(fs.path.join(constants.ROOT_DIR, "mscolab")) as mscolab_fs:
        # windows needs \\ or / but mixed is terrible. *nix needs /
        mscolab_fs.writetext(constants.MSCOLAB_CONFIG_FILE, config_string.replace('\\', '/'))
    path = fs.path.join(constants.ROOT_DIR, 'mscolab', constants.MSCOLAB_CONFIG_FILE)
    parent_path = fs.path.join(constants.ROOT_DIR, 'mscolab')

if not constants.SERVER_CONFIG_FS.exists(constants.MSCOLAB_AUTH_FILE):
    config_string = '''
import hashlib

class mscolab_auth(object):
     password = "testvaluepassword"
     allowed_users = [("user", hashlib.md5(password.encode('utf-8')).hexdigest())]
'''
    ROOT_FS = fs.open_fs(constants.ROOT_DIR)
    if not ROOT_FS.exists('mscolab'):
        ROOT_FS.makedir('mscolab')
    with fs.open_fs(fs.path.join(constants.ROOT_DIR, "mscolab")) as mscolab_fs:
        # windows needs \\ or / but mixed is terrible. *nix needs /
        mscolab_fs.writetext(constants.MSCOLAB_AUTH_FILE, config_string.replace('\\', '/'))


def _load_module(module_name, path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)


_load_module("mswms_settings", constants.SERVER_CONFIG_FILE_PATH)
_load_module("mscolab_settings", path)


@pytest.fixture(autouse=True)
def fail_if_open_message_boxes_left():
    """Fail a test if there are any Qt message boxes left open at the end
    """
    # Mock every MessageBox widget in the test suite to avoid unwanted freezes on unhandled error popups etc.
    with mock.patch("PyQt5.QtWidgets.QMessageBox.question") as q, \
            mock.patch("PyQt5.QtWidgets.QMessageBox.information") as i, \
            mock.patch("PyQt5.QtWidgets.QMessageBox.critical") as c, \
            mock.patch("PyQt5.QtWidgets.QMessageBox.warning") as w:
        yield
        if any(box.call_count > 0 for box in [q, i, c, w]):
            summary = "\n".join([f"PyQt5.QtWidgets.QMessageBox.{box()._extract_mock_name()}: {box.mock_calls[:-1]}"
                                 for box in [q, i, c, w] if box.call_count > 0])
            pytest.fail(f"An unhandled message box popped up during your test!\n{summary}")
    # Try to close all remaining widgets after each test
    for qobject in set(QtWidgets.QApplication.topLevelWindows() + QtWidgets.QApplication.topLevelWidgets()):
        try:
            qobject.destroy()
        # Some objects deny permission, pass in that case
        except RuntimeError:
            pass


@pytest.fixture(scope="session", autouse=True)
def configure_testsetup(request):
    if Display is not None:
        # needs for invisible window output xvfb installed,
        # default backend for visible output is xephyr
        # by visible=0 you get xvfb
        VIRT_DISPLAY = Display(visible=0, size=(1280, 1024))
        VIRT_DISPLAY.start()
        yield
        VIRT_DISPLAY.stop()
    else:
        yield

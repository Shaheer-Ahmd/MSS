# -*- coding: utf-8 -*-
"""

    tests._test_msui.test_mscolab_version_history
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This module is used to test mscolab-operation related gui.

    This file is part of MSS.

    :copyright: Copyright 2020 Tanish Grover
    :copyright: Copyright 2020-2023 by the MSS team, see AUTHORS.
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
import os
import sys
import pytest
import mock

from tests.utils import mscolab_start_server
from mslib.mscolab.conf import mscolab_settings
from PyQt5 import QtCore, QtTest, QtWidgets
from mslib.msui import mscolab
from mslib.msui import msui
from mslib.mscolab.mscolab import handle_db_reset
from mslib.mscolab.seed import add_user, get_user, add_operation, add_user_to_operation
from mslib.utils.config import modify_config_file


PORTS = list(range(20000, 20500))


@pytest.mark.skipif(os.name == "nt",
                    reason="multiprocessing needs currently start_method fork")
class Test_MscolabVersionHistory(object):
    def setup_method(self):
        handle_db_reset()
        self.process, self.url, self.app, _, self.cm, self.fm = mscolab_start_server(PORTS)
        self.userdata = 'UV10@uv10', 'UV10', 'uv10'
        self.operation_name = "europe"
        assert add_user(self.userdata[0], self.userdata[1], self.userdata[2])
        assert add_operation(self.operation_name, "test europe")
        assert add_user_to_operation(path=self.operation_name, emailid=self.userdata[0])
        self.user = get_user(self.userdata[0])
        QtTest.QTest.qWait(500)
        self.application = QtWidgets.QApplication(sys.argv)
        self.window = msui.MSUIMainWindow(mscolab_data_dir=mscolab_settings.MSCOLAB_DATA_DIR)
        self.window.create_new_flight_track()
        self.window.show()
        # connect and login to mscolab
        self._connect_to_mscolab()
        modify_config_file({"MSS_auth": {self.url: self.userdata[0]}})
        self._login(self.userdata[0], self.userdata[2])
        # activate operation and open chat window
        self._activate_operation_at_index(0)
        self.window.actionVersionHistory.trigger()
        QtWidgets.QApplication.processEvents()
        self.version_window = self.window.mscolab.version_window
        assert self.version_window is not None
        QtTest.QTest.qWaitForWindowExposed(self.window)
        QtWidgets.QApplication.processEvents()

    def teardown_method(self):
        self.window.mscolab.logout()
        if self.window.mscolab.version_window:
            self.window.mscolab.version_window.close()
        if self.window.mscolab.conn:
            self.window.mscolab.conn.disconnect()
        self.application.quit()
        QtWidgets.QApplication.processEvents()
        self.process.terminate()

    def test_changes(self):
        self._change_version_filter(1)
        len_prev = self.version_window.changes.count()
        # make a changes
        self.window.mscolab.waypoints_model.invert_direction()
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(100)
        self.window.mscolab.waypoints_model.invert_direction()
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(100)
        self.version_window.load_all_changes()
        QtWidgets.QApplication.processEvents()
        len_after = self.version_window.changes.count()
        assert len_prev == (len_after - 2)

    @mock.patch("PyQt5.QtWidgets.QInputDialog.getText", return_value=["MyVersionName", True])
    def test_set_version_name(self, mockbox):
        self._set_version_name()
        QtTest.QTest.qWait(100)
        assert self.version_window.changes.currentItem().version_name == "MyVersionName"
        assert self.version_window.changes.count() == 1

    @mock.patch("PyQt5.QtWidgets.QInputDialog.getText", return_value=["MyVersionName", True])
    def test_version_name_delete(self, mockbox):
        self._set_version_name()
        QtTest.QTest.qWait(100)
        assert self.version_window.changes.currentItem().version_name == "MyVersionName"
        QtTest.QTest.mouseClick(self.version_window.deleteVersionNameBtn, QtCore.Qt.LeftButton)
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(500)
        assert self.version_window.changes.count() == 1
        assert self.version_window.changes.currentItem().version_name is None

    @mock.patch("PyQt5.QtWidgets.QMessageBox.question", return_value=QtWidgets.QMessageBox.Yes)
    def test_undo_changes(self, mockbox):
        self._change_version_filter(1)
        # make changes
        for i in range(2):
            self.window.mscolab.waypoints_model.invert_direction()
            QtWidgets.QApplication.processEvents()
            QtTest.QTest.qWait(100)
        self.version_window.load_all_changes()
        QtWidgets.QApplication.processEvents()
        changes_count = self.version_window.changes.count()
        self._activate_change_at_index(1)
        QtTest.QTest.mouseClick(self.version_window.checkoutBtn, QtCore.Qt.LeftButton)
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(200)
        new_changes_count = self.version_window.changes.count()
        assert changes_count + 1 == new_changes_count

    def test_refresh(self):
        self._change_version_filter(1)
        changes_count = self.version_window.changes.count()
        self.window.mscolab.waypoints_model.invert_direction()
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(100)
        self.window.mscolab.waypoints_model.invert_direction()
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(100)
        QtTest.QTest.mouseClick(self.version_window.refreshBtn, QtCore.Qt.LeftButton)
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(100)
        new_changes_count = self.version_window.changes.count()
        assert new_changes_count == changes_count + 2

    def _connect_to_mscolab(self):
        self.connect_window = mscolab.MSColab_ConnectDialog(parent=self.window, mscolab=self.window.mscolab)
        self.window.mscolab.connect_window = self.connect_window
        assert self.connect_window is not None
        self.connect_window.urlCb.setEditText(self.url)
        self.connect_window.show()
        QtTest.QTest.mouseClick(self.connect_window.connectBtn, QtCore.Qt.LeftButton)
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(500)

    def _login(self, emailid, password):
        assert self.connect_window is not None
        self.connect_window.loginEmailLe.setText(emailid)
        self.connect_window.loginPasswordLe.setText(password)
        QtTest.QTest.mouseClick(self.connect_window.loginBtn, QtCore.Qt.LeftButton)
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(500)

    def _activate_operation_at_index(self, index):
        assert index < self.window.listOperationsMSC.count()
        item = self.window.listOperationsMSC.item(index)
        point = self.window.listOperationsMSC.visualItemRect(item).center()
        QtTest.QTest.mouseClick(self.window.listOperationsMSC.viewport(), QtCore.Qt.LeftButton, pos=point)
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.mouseDClick(self.window.listOperationsMSC.viewport(), QtCore.Qt.LeftButton, pos=point)
        QtWidgets.QApplication.processEvents()

    def _activate_change_at_index(self, index):
        assert self.version_window is not None
        assert index < self.version_window.changes.count()
        item = self.version_window.changes.item(index)
        point = self.version_window.changes.visualItemRect(item).center()
        QtTest.QTest.mouseClick(self.version_window.changes.viewport(), QtCore.Qt.LeftButton, pos=point)
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.keyClick(self.version_window.changes.viewport(), QtCore.Qt.Key_Return)
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(100)

    def _change_version_filter(self, index):
        assert self.version_window is not None
        assert index < self.version_window.versionFilterCB.count()
        self.version_window.versionFilterCB.setCurrentIndex(index)
        self.version_window.versionFilterCB.currentIndexChanged.emit(index)
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(100)

    def _set_version_name(self):
        self._change_version_filter(1)
        # make a changes
        self.window.mscolab.waypoints_model.invert_direction()
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.qWait(100)
        self.version_window.load_all_changes()
        QtWidgets.QApplication.processEvents()
        self._activate_change_at_index(0)
        QtWidgets.QApplication.processEvents()
        QtTest.QTest.mouseClick(self.version_window.nameVersionBtn, QtCore.Qt.LeftButton)
        QtWidgets.QApplication.processEvents()

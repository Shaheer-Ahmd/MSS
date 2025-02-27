# -*- coding: utf-8 -*-
"""

    mslib.mscolab.file_manager.py
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Code to handle file I/O in mscolab

    This file is part of MSS.

    :copyright: Copyright 2019 Shivashis Padhi
    :copyright: Copyright 2019-2023 by the MSS team, see AUTHORS.
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
import datetime
import fs
import difflib
import logging
import git
from sqlalchemy.exc import IntegrityError
from mslib.mscolab.models import db, Operation, Permission, User, Change, Message
from mslib.mscolab.conf import mscolab_settings


class FileManager:
    """Class with handler functions for file related functionalities"""

    def __init__(self, data_dir):
        self.data_dir = data_dir

    def create_operation(self, path, description, user, last_used=None, content=None, category="default", active=True):
        """
        path: path to the operation
        description: description of the operation
        """
        # set codes on these later
        if path.find("/") != -1 or path.find("\\") != -1 or (" " in path):
            logging.debug("malicious request: %s", user)
            return False
        proj_available = Operation.query.filter_by(path=path).first()
        if proj_available is not None:
            return False
        if last_used is None:
            last_used = datetime.datetime.utcnow()
        operation = Operation(path, description, last_used, category, active=active)
        db.session.add(operation)
        db.session.flush()
        operation_id = operation.id
        # this is the only insertion with "creator" access_level
        perm = Permission(user.id, operation_id, "creator")
        db.session.add(perm)
        db.session.commit()
        # here we can import the permissions from Group file
        if not path.endswith(mscolab_settings.GROUP_POSTFIX):
            import_op = Operation.query.filter_by(path=f"{category}{mscolab_settings.GROUP_POSTFIX}").first()
            if import_op is not None:
                self.import_permissions(import_op.id, operation_id, user.id)
        data = fs.open_fs(self.data_dir)
        data.makedir(operation.path)
        operation_file = data.open(fs.path.combine(operation.path, 'main.ftml'), 'w')
        if content is not None:
            operation_file.write(content)
        else:
            operation_file.write(mscolab_settings.STUB_CODE)
        operation_path = fs.path.combine(self.data_dir, operation.path)
        r = git.Repo.init(operation_path)
        r.git.clear_cache()
        r.index.add(['main.ftml'])
        r.index.commit("initial commit")
        return True

    def get_operation_details(self, op_id, user):
        """
        op_id: operation id
        user: authenticated user
        """
        if self.is_member(user.id, op_id):
            operation = Operation.query.filter_by(id=op_id).first()
            op = {
                "id": operation.id,
                "path": operation.path,
                "description": operation.description
            }
            return op
        return False

    def list_operations(self, user, skip_archived=False):
        """
        user: logged in user
        skip_archived: filter by active operations
        """
        operations = []
        permissions = Permission.query.filter_by(u_id=user.id).all()
        for permission in permissions:
            operation = Operation.query.filter_by(id=permission.op_id).first()
            if operation.last_used is not None and (
                    datetime.datetime.utcnow() - operation.last_used).days > mscolab_settings.ARCHIVE_THRESHOLD:
                # outdated OPs get archived
                self.update_operation(permission.op_id, "active", False, user)
            # new query to get uptodate data
            if skip_archived:
                operation = Operation.query.filter_by(id=permission.op_id, active=skip_archived).first()
            else:
                operation = Operation.query.filter_by(id=permission.op_id).first()

            if operation is not None:
                operations.append({
                    "op_id": permission.op_id,
                    "access_level": permission.access_level,
                    "path": operation.path,
                    "description": operation.description,
                    "category": operation.category,
                    "active": operation.active
                })
        return operations

    def is_member(self, u_id, op_id):
        """
        op_id: operation id
        u_id: user-id
        """
        # return true only if the user is a member
        perm = Permission.query.filter_by(u_id=u_id, op_id=op_id).first()
        if perm is None:
            return False
        return True

    def is_admin(self, u_id, op_id):
        """
        op_id: operation id
        u_id: user-id
        """
        # return true only if the user is admin
        perm = Permission.query.filter_by(u_id=u_id, op_id=op_id).first()
        if perm is None:
            return False
        elif perm.access_level != "admin":
            return False
        return True

    def is_creator(self, u_id, op_id):
        """
        op_id: operation id
        u_id: user-id
        """
        # return true only if the user is creator
        perm = Permission.query.filter_by(u_id=u_id, op_id=op_id).first()
        if perm is None:
            return False
        elif perm.access_level != "creator":
            return False
        return True

    def is_collaborator(self, u_id, op_id):
        """
        op_id: operation id
        u_id: user-id
        """
        # return true only if the user is collaborator
        perm = Permission.query.filter_by(u_id=u_id, op_id=op_id).first()
        if perm is None:
            return False
        elif perm.access_level != "collaborator":
            return False
        return True

    def is_viewer(self, u_id, op_id):
        """
        op_id: operation id
        u_id: user-id
        """
        # return true only if the user is viewer
        perm = Permission.query.filter_by(u_id=u_id, op_id=op_id).first()
        if perm is None:
            return False
        elif perm.access_level != "viewer":
            return False
        return True

    def auth_type(self, u_id, op_id):
        """
        op_id: operation id
        u_id: user-id
        """
        perm = Permission.query.filter_by(u_id=u_id, op_id=op_id).first()
        if perm is None:
            return False
        return perm.access_level

    def modify_user(self, user, attribute=None, value=None, action=None):
        if action == "create":
            user_query = User.query.filter_by(emailid=str(user.emailid)).first()
            if user_query is None:
                db.session.add(user)
                db.session.commit()
            else:
                return False
        elif action == "delete":
            user_query = User.query.filter_by(id=user.id).first()
            if user_query is not None:
                db.session.delete(user)
                db.session.commit()
            user_query = User.query.filter_by(id=user.id).first()
            # on delete we return succesfull deleted
            if user_query is None:
                return True
        elif action == "update_idp_user":
            user_query = User.query.filter_by(emailid=str(user.emailid)).first()
            if user_query is not None:
                db.session.add(user)
                db.session.commit()
            else:
                return False
        user_query = User.query.filter_by(id=user.id).first()
        if user_query is None:
            return False
        if None not in (attribute, value):
            if attribute == "emailid":
                user_query = User.query.filter_by(emailid=str(value)).first()
                if user_query is not None:
                    return False
            setattr(user, attribute, value)
            db.session.commit()
        return True

    def update_operation(self, op_id, attribute, value, user):
        """
        op_id: operation id
        attribute: attribute to be changed, eg path
        user: logged in user
        """
        if not self.is_admin(user.id, op_id) and not self.is_creator(user.id, op_id):
            return False
        operation = Operation.query.filter_by(id=op_id).first()
        if attribute == "path":
            if value.find("/") != -1 or value.find("\\") != -1 or (" " in value):
                logging.debug("malicious request: %s", user)
                return False
            data = fs.open_fs(self.data_dir)
            if data.exists(value):
                return False
            # will be move when operations are introduced
            # make a directory, else movedir
            data.makedir(value)
            data.movedir(operation.path, value)
            # when renamed to a Group operation
            if value.endswith(mscolab_settings.GROUP_POSTFIX):
                # getting the category
                category = value.split(mscolab_settings.GROUP_POSTFIX)[0]
                # all operation with that category
                ops_category = Operation.query.filter_by(category=category)
                for ops in ops_category:
                    # the user changing the {category}{mscolab_settings.GROUP_POSTFIX} needs to have rights in the op
                    # then members of this op gets added to all others of same category
                    self.import_permissions(op_id, ops.id, user.id)
        setattr(operation, attribute, value)
        db.session.commit()
        return True

    def delete_operation(self, op_id, user):
        """
        op_id: operation id
        user: logged in user
        """
        if self.auth_type(user.id, op_id) != "creator":
            return False
        Permission.query.filter_by(op_id=op_id).delete()
        Change.query.filter_by(op_id=op_id).delete()
        Message.query.filter_by(op_id=op_id).delete()
        operation = Operation.query.filter_by(id=op_id).first()
        with fs.open_fs(self.data_dir) as operation_dir:
            operation_dir.removetree(operation.path)
        db.session.delete(operation)
        db.session.commit()
        return True

    def get_authorized_users(self, op_id):
        """
        op_id: operation-id
        """
        permissions = Permission.query.filter_by(op_id=op_id).all()
        users = []
        for permission in permissions:
            user = User.query.filter_by(id=permission.u_id).first()
            users.append({"username": user.username, "access_level": permission.access_level})
        return users

    def save_file(self, op_id, content, user, comment=""):
        """
        op_id: operation-id,
        content: content of the file to be saved
        # ToDo save change in schema
        """
        # ToDo use comment
        operation = Operation.query.filter_by(id=op_id).first()
        if not operation:
            return False

        with fs.open_fs(self.data_dir) as data:
            """
            old file is read, the diff between old and new is calculated and stored
            as 'Change' in changes table. comment for each change is optional
            """
            old_data = data.readtext(fs.path.combine(operation.path, 'main.ftml'))
            old_data_lines = old_data.splitlines()
            content_lines = content.splitlines()
            diff = difflib.unified_diff(old_data_lines, content_lines, lineterm='')
            diff_content = '\n'.join(list(diff))
            data.writetext(fs.path.combine(operation.path, 'main.ftml'), content)
        # commit changes if comment is not None
        if diff_content != "":
            # commit to git repository
            operation_path = fs.path.combine(self.data_dir, operation.path)
            repo = git.Repo(operation_path)
            repo.git.clear_cache()
            repo.index.add(['main.ftml'])
            cm = repo.index.commit("committing changes")
            # change db table
            change = Change(op_id, user.id, cm.hexsha)
            db.session.add(change)
            db.session.commit()
            return True
        return False

    def get_file(self, op_id, user):
        """
        op_id: operation-id
        user: user of this request
        """
        perm = Permission.query.filter_by(u_id=user.id, op_id=op_id).first()
        if perm is None:
            return False
        operation = Operation.query.filter_by(id=op_id).first()
        if operation is None:
            return False
        with fs.open_fs(self.data_dir) as data:
            operation_file = data.open(fs.path.combine(operation.path, 'main.ftml'), 'r')
            operation_data = operation_file.read()
        return operation_data

    def get_all_changes(self, op_id, user, named_version=False):
        """
        op_id: operation-id
        user: user of this request

        Get all changes, mostly to be used in the chat window, in the side panel
        to render the recent changes.
        """
        perm = Permission.query.filter_by(u_id=user.id, op_id=op_id).first()
        if perm is None:
            return False
        # Get only named versions
        if named_version:
            changes = Change.query\
                .filter(Change.op_id == op_id)\
                .filter(~Change.version_name.is_(None))\
                .order_by(Change.created_at.desc())\
                .all()
        # Get all changes
        else:
            changes = Change.query\
                .filter_by(op_id=op_id)\
                .order_by(Change.created_at.desc())\
                .all()

        return list(map(lambda change: {
            'id': change.id,
            'comment': change.comment,
            'version_name': change.version_name,
            'username': change.user.username,
            'created_at': change.created_at.strftime("%Y-%m-%d, %H:%M:%S")
        }, changes))

    def get_change_content(self, ch_id, user):
        """
        ch_id: change id
        user: user of this request

        Get change related to id
        """
        ch = Change.query.filter_by(id=ch_id).first()
        perm = Permission.query.filter_by(u_id=user.id, op_id=ch.op_id).first()
        if perm is None:
            return False

        change = Change.query.filter_by(id=ch_id).first()
        if not change:
            return False
        operation = Operation.query.filter_by(id=change.op_id).first()
        operation_path = fs.path.combine(self.data_dir, operation.path)
        repo = git.Repo(operation_path)
        change_content = repo.git.show(f'{change.commit_hash}:main.ftml')
        return change_content

    def set_version_name(self, ch_id, op_id, u_id, version_name):
        if (not self.is_admin(u_id, op_id) and not self.is_creator(u_id, op_id) and not
                self.is_collaborator(u_id, op_id)):
            return False
        Change.query\
            .filter(Change.id == ch_id)\
            .update({Change.version_name: version_name}, synchronize_session=False)
        db.session.commit()
        return True

    def undo_changes(self, ch_id, user):
        """
        ch_id: change-id
        user: user of this request

        Undo a change
        # ToDo add a revert option, which removes only that commit's change
        """
        ch = Change.query.filter_by(id=ch_id).first()
        if (not self.is_admin(user.id, ch.op_id) and not self.is_creator(user.id, ch.op_id) and not
                self.is_collaborator(user.id, ch.op_id)):
            return False
        if ch is None:
            return False
        operation = Operation.query.filter_by(id=ch.op_id).first()
        if not ch or not operation:
            return False

        operation_path = fs.path.join(self.data_dir, operation.path)
        repo = git.Repo(operation_path)
        repo.git.clear_cache()
        try:
            file_content = repo.git.show(f'{ch.commit_hash}:main.ftml')
            with fs.open_fs(operation_path) as proj_fs:
                proj_fs.writetext('main.ftml', file_content)
            repo.index.add(['main.ftml'])
            cm = repo.index.commit(f"checkout to {ch.commit_hash}")
            change = Change(ch.op_id, user.id, cm.hexsha)
            db.session.add(change)
            db.session.commit()
            return True
        except Exception as ex:
            logging.debug(ex)
            return False

    def fetch_users_without_permission(self, op_id, u_id):
        if not self.is_admin(u_id, op_id) and not self.is_creator(u_id, op_id):
            return False

        user_list = User.query\
            .join(Permission, (User.id == Permission.u_id) & (Permission.op_id == op_id), isouter=True) \
            .add_columns(User.id, User.username) \
            .filter(Permission.u_id.is_(None))

        users = [[user.username, user.id] for user in user_list]
        return users

    def fetch_users_with_permission(self, op_id, u_id):
        if not self.is_admin(u_id, op_id) and not self.is_creator(u_id, op_id):
            return False

        user_list = User.query\
            .join(Permission, User.id == Permission.u_id)\
            .add_columns(User.id, User.username, Permission.access_level) \
            .filter(Permission.op_id == op_id) \
            .filter((User.id != u_id) & (Permission.access_level != 'creator'))

        users = [[user.username, user.access_level, user.id] for user in user_list]
        return users

    def fetch_operation_creator(self, op_id, u_id):
        if not self.is_admin(u_id, op_id) and not self.is_creator(u_id, op_id):
            return False
        current_operation_creator = Permission.query.filter_by(op_id=op_id, access_level="creator").first()
        return current_operation_creator.user.username

    def add_bulk_permission(self, op_id, user, new_u_ids, access_level):
        if not self.is_admin(user.id, op_id) and not self.is_creator(user.id, op_id):
            return False

        new_permissions = []
        for u_id in new_u_ids:
            if Permission.query.filter_by(u_id=u_id, op_id=op_id).first() is None:
                new_permissions.append(Permission(u_id, op_id, access_level))
        db.session.add_all(new_permissions)
        operation = Operation.query.filter_by(id=op_id).first()
        if operation.path.endswith(mscolab_settings.GROUP_POSTFIX):
            # the members of this gets added to all others of same category
            category = operation.path.split(mscolab_settings.GROUP_POSTFIX)[0]
            # all operation with that category
            ops_category = Operation.query.filter_by(category=category)
            new_permissions = []
            for ops in ops_category:
                if not ops.path.endswith(mscolab_settings.GROUP_POSTFIX):
                    new_permissions.append(Permission(u_id, ops.id, access_level))
                db.session.add_all(new_permissions)
        try:
            db.session.commit()
            return True
        except IntegrityError:
            db.session.rollback()
            return False

    def modify_bulk_permission(self, op_id, user, u_ids, new_access_level):
        if not self.is_admin(user.id, op_id) and not self.is_creator(user.id, op_id):
            return False

        # TODO: Check whether we need synchronize_session False Or Fetch
        Permission.query\
            .filter(Permission.op_id == op_id)\
            .filter(Permission.u_id.in_(u_ids))\
            .update({Permission.access_level: new_access_level}, synchronize_session='fetch')

        operation = Operation.query.filter_by(id=op_id).first()
        if operation.path.endswith(mscolab_settings.GROUP_POSTFIX):
            # the members of this gets added to all others of same category
            category = operation.path.split(mscolab_settings.GROUP_POSTFIX)[0]
            # all operation with that category
            ops_category = Operation.query.filter_by(category=category)
            for ops in ops_category:
                Permission.query \
                    .filter(Permission.op_id == ops.id) \
                    .filter(Permission.u_id.in_(u_ids)) \
                    .update({Permission.access_level: new_access_level}, synchronize_session='fetch')
        try:
            db.session.commit()
            return True
        except IntegrityError:
            db.session.rollback()
            return False

    def delete_bulk_permission(self, op_id, user, u_ids):
        # if the user is not a member of the operation, return false
        if not self.is_member(user.id, op_id):
            return False
        elif not self.is_admin(user.id, op_id) and not self.is_creator(user.id, op_id):
            # if the user is a member but non-admin and non-creator, and is trying to remove any other user
            if len(u_ids) != 1 or user.id not in u_ids:
                return False
        else:
            # if the user is admin or creator and is trying to remove a user not in this operation
            for u_id in u_ids:
                if not self.is_member(u_id, op_id):
                    return False
            if self.is_creator(user.id, op_id):
                # if the user is creator and is trying to leave the operation, return false
                if user.id in u_ids:
                    return False

        Permission.query \
            .filter(Permission.op_id == op_id) \
            .filter(Permission.u_id.in_(u_ids)) \
            .delete(synchronize_session='fetch')

        operation = Operation.query.filter_by(id=op_id).first()
        if operation.path.endswith(mscolab_settings.GROUP_POSTFIX):
            # the members of this gets added to all others of same category
            category = operation.path.split(mscolab_settings.GROUP_POSTFIX)[0]
            # all operation with that category
            ops_category = Operation.query.filter_by(category=category)
            for ops in ops_category:
                Permission.query \
                    .filter(Permission.op_id == ops.id) \
                    .filter(Permission.u_id.in_(u_ids)) \
                    .delete(synchronize_session='fetch')

        db.session.commit()
        return True

    def import_permissions(self, import_op_id, current_op_id, u_id):
        if not self.is_creator(u_id, current_op_id) and not self.is_admin(u_id, current_op_id):
            return False, None, "Not the creator or admin of this operation"

        perm = Permission.query.filter_by(u_id=u_id, op_id=import_op_id).first()
        if perm is None:
            return False, None, "Not a member of this operation"

        existing_perms = Permission.query \
            .filter(Permission.op_id == current_op_id) \
            .filter((Permission.u_id != u_id) & (Permission.access_level != 'creator')) \
            .all()
        existing_users = set([perm.u_id for perm in existing_perms])

        current_operation_creator = Permission.query.filter_by(op_id=current_op_id, access_level="creator").first()
        import_perms = Permission.query\
            .filter(Permission.op_id == import_op_id)\
            .filter((Permission.u_id != u_id) & (Permission.u_id != current_operation_creator.u_id))\
            .all()
        import_users = set([perm.u_id for perm in import_perms])

        is_perm = []
        for perm in existing_perms:
            is_perm.append((perm.u_id, perm.access_level))
        new_perm = []
        for perm in import_perms:
            access_level = perm.access_level
            # we keep creator to the one created the operation, and substitute the imported to admin
            if perm.access_level == "creator":
                access_level = "admin"
            new_perm.append((perm.u_id, access_level))

        if sorted(new_perm) == sorted(is_perm):
            return False, None, "Permissions are already given"

        # We Delete all permissions of existing users which not in new permission
        delete_users = []
        for perm in existing_perms:
            if (perm.u_id, perm.access_level) not in new_perm:
                db.session.delete(perm)
                delete_users.append(perm.u_id)

        db.session.flush()

        # Then add the permissions of the imported operation based on new_perm
        new_users = []
        for u_id, access_level in new_perm:
            if not (u_id, access_level) in is_perm:
                new_users.append(u_id)
                if Permission.query.filter_by(u_id=u_id, op_id=current_op_id).first() is None:
                    db.session.add(Permission(u_id, current_op_id, access_level))

        # prepare events based on action done
        delete_users = list(existing_users.difference(import_users))
        add_users = list(import_users.difference(existing_users))
        modify_users = []
        _intersect_users = import_users.intersection(existing_users)
        _new_perm = dict(new_perm)
        _is_perm = dict(is_perm)
        for m_uid in _intersect_users:
            if _new_perm[m_uid] != _is_perm[m_uid]:
                modify_users.append(m_uid)

        try:
            db.session.commit()
            return True, {"add_users": add_users, "modify_users": modify_users, "delete_users": delete_users}, "success"

        except IntegrityError:
            db.session.rollback()
            return False, None, "Some error occurred! Could not import permissions. Please try again."

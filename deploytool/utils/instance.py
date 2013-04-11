import os
import json

from fabric.api import *
from fabric.colors import *
from fabric.contrib.files import *

from deploytool.db import get_database_operations

import commands


def get_obsolete_instances(vhost_path):
    """ Return obsolete instances from remote server """

    try:
        with cd(vhost_path):

            # list directories, display name only, sort by ctime, filter by git-commit-tag-length
            command = 'ls -1tcd */ | awk \'{ if(length($1) == 41) { print $1 }}\''

            # split into list and return everything but the 3 newest instances
            return run(command).split()[3:]
    except:
        return []


def prune_obsolete_instances():
    """ Find old instances and remove them to free up space """

    removed_instances = []

    for instance in get_obsolete_instances(env.vhost_path):
        is_current = bool(get_instance_stamp(env.current_instance_path) == instance)
        is_previous = bool(get_instance_stamp(env.previous_instance_path) == instance)

        if not (is_current or is_previous):
            commands.delete(os.path.join(env.vhost_path, instance))
            removed_instances.append(instance)

    if removed_instances:
        print(green('\nThese old instances were removed from remote filesystem:'))
        print(removed_instances)


def backup_database(file_path):
    database_operations = get_database_operations(env.database_engine)
    credentials = get_database_credentials()

    database_operations.backup_database(
        credentials['database'],
        credentials['username'],
        credentials['password'],
        file_path
    )


def restore_database(file_path):
    """ Drop, create, restore """

    database_operations = get_database_operations(env.database_engine)
    credentials = get_database_credentials()

    database_operations.restore_database(
        credentials['database'],
        credentials['username'],
        credentials['password'],
        file_path
    )


def create_virtualenv(virtualenv_path):
    """ Creates virtual environment for instance """

    run('virtualenv %s --no-site-packages' % virtualenv_path)


def pip_install_requirements(virtualenv_path, requirements_path, cache_path, log_path):
    """ Requires availability of Pip (0.8.1 or later) on remote system """

    requirements_file = os.path.join(requirements_path, 'requirements.txt')
    log_file = os.path.join(log_path, 'pip.log')

    if not exists(requirements_file) or not exists(virtualenv_path):
        abort(red('Could not install packages. Virtual environment or requirements.txt not found.'))

    args = (virtualenv_path, requirements_file, cache_path, log_file)
    run('%s/bin/pip install -r %s --download-cache=%s --use-mirrors --quiet --log=%s' % args)


def get_instance_stamp(instance_path):
    """ Reads symlinked (current/previous) instance and returns its sliced off stamp (git commit SHA1)  """

    return commands.read_link(instance_path)[-40:]


def set_current_instance(vhost_path, instance_path):
    """ Delete previous, set current to previous and new to current """

    with cd(vhost_path):
        commands.delete('./previous_instance')

        if exists('./current_instance'):
            commands.rename('./current_instance', './previous_instance')

        commands.create_symbolic_link(instance_path, './current_instance')


def rollback(vhost_path):
    """ Updates symlinks: Remove current instance and rename previous to current """

    with cd(vhost_path):
        if exists('./previous_instance'):
            commands.delete('./current_instance')
            commands.rename('./previous_instance', './current_instance')


def get_database_credentials():
    credentials_filename = 'credentials.json'

    get(
        os.path.join(env.vhost_path, credentials_filename),
        credentials_filename
    )

    with open(credentials_filename) as f:
        credentials = json.load(f)

    os.remove(credentials_filename)
    return credentials

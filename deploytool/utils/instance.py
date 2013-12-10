from datetime import datetime
import uuid
import os

from fabric.api import run, cd, env, abort
from fabric.colors import green, red
from fabric.contrib.files import exists

from . import commands
from . import postgresql


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
    project_name = get_project_name()

    postgresql.backup_database(
        database_name=project_name,
        username=project_name,
        file_path=file_path
    )


def restore_database(file_path):
    project_name = get_project_name()

    postgresql.restore_database(
        database_name=project_name,
        username=project_name,
        file_path=file_path
    )


def backup_and_download_database(local_output_filename=''):
    def generate_output_file():
        timestamp = datetime.today().strftime('%y%m%d%H%M')
        return '%s%s_%s.sql' % (env.project_name_prefix, env.database_name, timestamp)

    if not local_output_filename:
        local_output_filename = generate_output_file()

    remote_filename = os.path.join(env.backup_path, str(uuid.uuid4()))

    print(green('\nCreating backup.'))
    backup_database(remote_filename)

    print(green('\nDownloading and removing remote backup.'))
    commands.download_file(remote_filename, local_output_filename)

    return os.path.join(os.getcwd(), local_output_filename)


def create_virtualenv(virtualenv_path):
    """ Creates virtual environment for instance """

    run('virtualenv %s --no-site-packages --setuptools' % virtualenv_path)


def pip_install_requirements(virtualenv_path, requirements_path, cache_path, log_path, use_wheel=False):
    """ Requires availability of Pip (0.8.1 or later) on remote system """

    requirements_file = os.path.join(requirements_path, 'requirements.txt')
    log_file = os.path.join(log_path, 'pip.log')

    if not exists(requirements_file) or not exists(virtualenv_path):
        abort(red('Could not install packages. Virtual environment or requirements.txt not found.'))

    arguments = [
        '%s/bin/pip' % virtualenv_path,
        'install',
        '-r',
        requirements_file,
        '--quiet',
        '--log=%s' % log_file,
    ]

    if use_wheel:
        arguments += [
            '--use-wheel',
            '--find-links=/opt/wheels',
            '--no-index'
        ]
    else:
        arguments += [
            '--download-cache=%s' % cache_path,
            '--use-mirrors'
        ]

    run(' '.join(arguments))


def pip_install_package(virtualenv_path, package, version, cache_path, log_path, use_wheel=False):
    """ Install this python package using pip """

    if not exists(virtualenv_path):
        abort(red('Could not install package. Virtual environment not found.'))

    # todo: add run_pip function?
    log_file = os.path.join(log_path, 'pip.log')

    arguments = [
        '%s/bin/pip' % virtualenv_path,
        'install',
        '%s==%s' % (package, version),
        '--quiet',
        '--log=%s' % log_file,
    ]

    if use_wheel:
        arguments += [
            '--use-wheel',
            '--find-links=/opt/wheels',
            '--no-index'
        ]
    else:
        arguments += [
            '--download-cache=%s' % cache_path,
            '--use-mirrors'
        ]

    run(' '.join(arguments))


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


def get_project_name():
    """
    Get the project name including prefix. For example 't-aurea' for the aurea test site.
    """
    return '%s%s' % (env.project_name_prefix, env.project_name)
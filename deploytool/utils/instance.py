from datetime import datetime
import uuid
import os
import re

from fabric.api import run, cd, env, abort
from fabric.colors import green, red
from fabric.contrib.files import exists, append

from . import commands
from . import postgresql


def get_unused_instances(vhost_path):
    """
    Return instance directories that are not the current or the previous instance.
    The list is sorted reversed by datetime
    """
    current_direcory_names = [
        get_instance_stamp(os.path.join(vhost_path, 'current_instance')),
        get_instance_stamp(os.path.join(vhost_path, 'previous_instance'))
    ]
    re_instance = re.compile(r'[a-z0-9]{40}(_\d+)?')

    def is_valid_path(directory):
        directory_name = os.path.basename(os.path.dirname(directory))

        if directory_name in current_direcory_names:
            return False
        else:
            return bool(
                re_instance.match(directory_name)
            )

    try:
        # - t: sort by modification time, newest first
        directories = get_directories(vhost_path, 't')

        return [
            directory for directory in directories if is_valid_path(directory)
        ]
    except:
        return []


def ls(path, options=''):
    # run ls with '-1' option wich results in 1 file per line in output
    output = run('ls -1%s %s' % (options, path))

    files = output.split("\n")

    return [f.strip() for f in files]


def get_directories(path, options=''):
    # - d: filter directories; must add */ to path for this
    return ls(
        os.path.join(path, '*/'),
        'd%s' % options
    )


def prune_obsolete_instances(vhost_path):
    """ Find old instances and remove them to free up space """

    removed_instances = []
    unused_instances = get_unused_instances(vhost_path)

    # Delete all instances except first 3
    for instance in unused_instances[3:]:
        commands.delete(os.path.join(vhost_path, instance))
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

    remote_filename = os.path.join('/tmp/', str(uuid.uuid4()))

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


def get_instance_stamp(symbolic_link):
    """ Reads symlinked (current/previous) instance and returns its sliced off stamp (git commit SHA1)  """

    instance_path = commands.read_link(symbolic_link)

    if not instance_path:
        return ''
    else:
        directory_name = os.path.basename(instance_path)

        # The directory name can be a stamp or [sha1]_[index]

        match = re.match(r'([a-z0-9]{40})(_\d+)?', directory_name)

        if not match:
            raise Exception('Could not get stamp from directory %s and symbolic link %s' % (instance_path, symbolic_link))

        return match.groups()[0]


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


def log(success, task_name, stamp, log_path):
    """ Single line task logging to ./log/fabric.log """

    if success is True:
        result = 'success'
    else:
        result = 'failed'

    message = '[%s] %s %s in %s by %s for %s' % (
        datetime.today().strftime('%Y-%m-%d %H:%M'),
        task_name,
        result,
        env.environment,
        env.local_user,
        stamp
    )

    append(os.path.join(log_path, 'fabric.log'), message)

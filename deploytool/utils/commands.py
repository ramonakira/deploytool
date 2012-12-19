from fabric.api import *
from fabric.colors import *
from fabric.contrib.files import *
import os


def get_folder_size(path):
    """ Returns human-readable string with total recursive size of path """

    return run('du -h --summarize %s' % path)


def get_changed_files(local_stamp, remote_stamp, show_full_diff=False):
    """ Returns git diff from remote commit hash vs local HEAD commit hash """

    options = ''
    if not show_full_diff:
        options = options + '--stat'

    git_diff = 'git diff %s %s %s' % (options, remote_stamp, local_stamp, )

    output = local(git_diff, capture=True)
    output = [c.strip() for c in output.split('\n') if c != '']

    if not output:
        return 'No changed files found.'
    else:
        output = '\n'.join(str(i) for i in output)
        if show_full_diff:
            output = output + '\n\nExecuted git diff:\n' + git_diff
        return output


def remote_stamp_in_local_repo(remote_stamp):
    """ Check if `remote_stamp` exists in local repository """

    return local('git branch --contains %s' % remote_stamp, capture=True)


def create_tarball(vhost_path, target, file_name='archive.tar'):
    """ Create archive from target file/folder """

    with cd(vhost_path):
        run('tar -cf ./%s ./%s' % (file_name, target))


def download_file(remote_path, local_path, delete_remote=True):

    get(remote_path, local_path)

    if delete_remote:
        delete(remote_path)


def tail_file(file_path, lines=5):
    """ Output the last lines from a file to console """

    return run('tail --lines=%d %s' % (lines, file_path))


def read_link(path):
    """ Returns real path for symbolic link """

    if exists(path):
        return run('readlink -f %s' % path).strip()
    else:
        return ''


def create_folder(path):

    if exists(path):
        abort(red('Path `%s` already exists.' % path))
    else:
        run('mkdir %s' % path)


def delete(path):

    run('rm -rf %s' % path)


def create_symbolic_link(real_path, symbolic_path):

    run('ln -sf %s %s' % (real_path, symbolic_path))


def copy(from_path, to_path):

    run('cp %s %s' % (from_path, to_path))


def rename(old_path, new_path):

    run('mv %s %s' % (old_path, new_path))


def touch_wsgi(vhost_path):
    """ Touch WSGI to restart website """

    return run('touch %s/django.wsgi' % vhost_path)


def python_run(virtualenv_path, command):
    """ Execute Python commands for current virtual environment """

    return run('%s/bin/python %s' % (virtualenv_path, command))


def django_manage(virtualenv_path, project_path, command):
    """ Execute Django management command """

    python_path = os.path.join(project_path, 'manage.py')
    python_command = '%s %s' % (python_path, command)
    python_run(virtualenv_path, python_command)


def sql_execute_query(virtualenv_path, scripts_path, query):
    """ Execute mysql command for supplied query """

    python_command = '%s/sql_query.py "%s"' % (scripts_path, query)
    python_run(virtualenv_path, python_command)


def sql_execute_file(virtualenv_path, scripts_path, filename):
    """ Execute mysql file """

    python_command = '%s/sql_file.py "%s"' % (scripts_path, filename)
    python_run(virtualenv_path, python_command)

import os

from fabric.api import *
from fabric.colors import *
from fabric.contrib.files import *

import deploytool


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


def python_run(virtualenv_path, command, sudo_username):
    """ Execute Python commands for current virtual environment """

    full_command = '%s/bin/python %s' % (virtualenv_path, command)

    if sudo_username:
        return sudo(full_command, user=sudo_username)
    else:
        return run(full_command)


def django_manage(virtualenv_path, project_path, command, sudo_username=None):
    """ Execute Django management command """

    with cd(project_path):
        python_command = 'manage.py %s' % command
        python_run(virtualenv_path, python_command, sudo_username)


def upload_jinja_template(filenames, destination, context, template_paths):
    """
    Upload a template. Generate the file using a jinja2 template.
    This function does almost the same as the upload_template function in fabric.

    Differences:
    - accepts multiple template paths
    - accepts multiple filenames
    - assumes some defaults (sudo, backup=True)
    """
    # Process template
    from jinja2 import Environment, FileSystemLoader

    text = ''
    try:
        jenv = Environment(loader=FileSystemLoader(template_paths))
        text = jenv.select_template(filenames).render(**context or {})
    except ImportError:
        import traceback
        tb = traceback.format_exc()
        abort(tb + "\nUnable to import Jinja2 -- see above.")

    # Back up original file
    if exists(destination):
        sudo("cp %s{,.bak}" % destination)

    # Upload the file.
    return put(
        local_path=StringIO(text),
        remote_path=destination,
        use_sudo=True
    )


def get_local_templates_path():
    return os.path.join(os.path.dirname(deploytool.__file__), 'templates')


def get_template_paths():
    paths = []

    if 'templates_path' in env:
        paths.append(env.templates_path)

    paths.append(get_local_templates_path())

    return paths


def get_python_version():
    """
    Return python version as <major>.<minor> string.
    E.g. '2.6'
    """
    command = "python -c \"import sys;print '%s.%s' % (sys.version_info.major, sys.version_info.minor)\""

    return run(command)


def restart_supervisor_job(job_name):
    """
    Restart a job using supervisor; this requires sudo.
    """
    run('supervisorctl restart %s' % job_name)


def restart_gunicorn():
    job_name = '%s%s' % (env.project_name_prefix, env.project_name)
    restart_supervisor_job(job_name)
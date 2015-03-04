from fabric.api import run, local, get, cd, abort, sudo, env
from fabric.colors import red
from fabric.contrib.files import exists


def get_folder_size(path):
    """ Returns human-readable string with total recursive size of path """

    return run('du -h --summarize %s' % path)


def get_file_size(path):
    """
    Returns file size for regular files.
    Returns -1 if file does not exist or path is not a regular file (e.g. dir or symlink)
    """
    return int(run("if [ -f {0} ] && [ ! -h {0} ]; then stat -c %s {0}; else echo '-1'; fi".format(path)))


def get_changed_files(local_stamp, remote_stamp, show_full_diff=False):
    """ Returns git diff from remote commit hash vs local HEAD commit hash """

    options = ''
    if not show_full_diff:
        options += '--stat'

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


def rotate_log(log_path, max_bytes=0, backups=0):
    """
    Rotates a log file.

    Rotation only happens if the given file path exists, and is >= max_bytes.

    If backups is > 0 log_path will be copied to log_path + .1, previous backups to log_path.n + 1 etc.

    Finally the file in log_path will be truncated.
    """
    file_size = get_file_size(log_path)
    if max_bytes and file_size >= max_bytes:
        if backups > 0:
            for i in xrange(backups - 1, 0, -1):
                source_path = "%s.%d" % (log_path, i)
                dest_path = "%s.%d" % (log_path, i + 1)
                if exists(source_path):
                    if exists(dest_path):
                        delete(dest_path)
                    rename(source_path, dest_path)
            dest_path = log_path + ".1"
            if exists(dest_path):
                delete(dest_path)
            copy(log_path, dest_path)
        run("> %s" % log_path)


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


def get_python_version():
    """
    Return python version as <major>.<minor> string.
    E.g. '2.6'
    """
    command = "python -c \"import sys;print '%s.%s' % (sys.version_info.major, sys.version_info.minor)\""

    return run(command)


def run_supervisor(vhost_path, parameters):
    """
    Run supervisor with these parameters.

    run_supervisor('restart all')
    """
    config_file = '%s/supervisor/supervisor.conf' % vhost_path

    run('supervisorctl -c %s %s' % (config_file, parameters))


def restart_supervisor_jobs(vhost_path, restart_services=None):
    if not restart_services:
        restart_services = ['all']

    run_supervisor(vhost_path, 'restart %s' % ' '.join(restart_services))


def stop_supervisor_jobs(vhost_path):
    run_supervisor(vhost_path, 'stop all')


def start_supervisor_jobs(vhost_path):
    run_supervisor(vhost_path, 'start all')


def collect_static(virtualenv_path, source_path, create_symbolic_links=True):
    parameters = [
        '--noinput',
        '--verbosity=0',
        '--traceback',
    ]

    if create_symbolic_links:
        parameters.append('--link')

    django_manage(
        virtualenv_path,
        source_path,
        'collectstatic %s' % ' '.join(parameters)
    )

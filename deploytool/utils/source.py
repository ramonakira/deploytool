from fabric.api import *
from fabric.colors import *


def transfer_source(upload_path, tree):
    """
    Archive source and upload/extract to/on remote server
        upload_path =>  target location to extract on remote
        tree        =>  git ID for branch, commit or tag
    """

    tar_file = 'source.tar'
    local('git archive --format=tar --output=%s %s' % (tar_file, tree))
    uploaded_files = put(tar_file, upload_path)

    if uploaded_files.succeeded:
        with cd(upload_path):
            run('tar -xf %s' % uploaded_files[0])
            run('rm -f ./%s' % tar_file)
        local('rm -f ./%s' % tar_file)


def compass_compile(upload_path, tree, compass_version):
    """
    Check your local compass version
    Compile compass project locally
    Upload local static dir to remote
    """

    local_compass_version = local('compass _' + compass_version + '_ version -q', capture=True)
    if (local_compass_version == compass_version):
        local_tmp_dir = '.compass_compile_tmp'
        local_tmp_tar = 'compass_compile_tmp.tar'

        local('git archive --output=%s %s' % (local_tmp_tar, tree))
        local('mkdir -p %s' % local_tmp_dir)
        local('tar -C %s -xf %s' % (local_tmp_dir, local_tmp_tar))
        local('compass _' + compass_version + '_ clean && compass _' + compass_version + '_ compile %s --environment production' % local_tmp_dir)

        local_static_tar = 'static.tar'
        local('tar -C %s -cf %s %s' % (local_tmp_dir, local_static_tar, 'static'))
        upload_static = put(local_static_tar, upload_path)

        # upload static files
        if upload_static.succeeded:
            with cd(upload_path):
                run('tar -xf %s' % upload_static[0])
                run('rm -f ./%s' % local_static_tar)

            # remove local .tmp dir and tar files, recompile compass project
            local('rm -f %s' % local_tmp_tar)
            local('rm -f %s' % local_static_tar)
            local('rm -rf %s' % local_tmp_dir)
            local('compass _' + compass_version + '_ clean && compass _' + compass_version + '_ compile')
        else:
            abort(red('Deploy aborted because compass compiling failed.'))
    else:
        abort(red('Deploy aborted because your local compass version is different from deploy settings.'))


def create_tag(tag):

    local('git tag %s' % tag)
    local('git push --tags')


def delete_tag(tag):

    local('git tag -d %s' % tag)
    local('git push origin :refs/tags/%s' % tag)


def list_tags():
    """
    Uses subprocess to pipe the output of `git tag` to a variable.
    The tags are split to a list, converted to integers and reversed.
    """

    output = local('git tag', capture=True)
    tags = [int(t) for t in output.split('\n') if t != '']
    tags.reverse()

    return tags


def list_commits(amount=10, branch='master'):
    """ Pipe git commit log to list """

    output = local('git log %s -n %d --pretty=format:%%H' % (branch, amount), capture=True)
    return [c.strip() for c in output.split('\n') if c != '']


def get_branch_name():

    return local('git rev-parse --abbrev-ref HEAD', capture=True).strip()


def get_commit_id(tree):

    return local('git rev-parse %s' % tree, capture=True).strip()


def get_head():

    return get_commit_id('HEAD')

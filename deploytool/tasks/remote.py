import os
import sys
import uuid

from fabric.operations import require, local, open_shell, put, sudo
from fabric.tasks import Task
from fabric.api import env, settings, hide, abort
from fabric.colors import green, red, magenta, yellow
from fabric.contrib.files import exists
from fabric.contrib.console import confirm
from fabric.contrib import django

import deploytool.utils as utils
from deploytool.utils import commands
from deploytool.utils.instance import backup_and_download_database, ls
from deploytool.utils.deploy import WebsiteDeployment


class RemoteHost(Task):
    """ HOST """

    requirements = [
        'environment',
        'hosts',
        'project_name',
        'project_name_prefix',
        'vhosts_path',
    ]

    def __init__(self, *args, **kwargs):
        super(RemoteHost, self).__init__(*args, **kwargs)

        # use environment as task name
        self.name = kwargs['settings']['environment']

        # save project settings in instance
        self.settings = kwargs['settings']

    def run(self):

        # update fabric environment for project settings
        env.update(self.settings)

        # check if all required project settings are present in fabric environment
        [require(r) for r in self.requirements]

        vhost_folder = '%s%s' % (env.project_name_prefix, env.project_name)
        vhost_path = os.path.join(env.vhosts_path, vhost_folder)

        print(green('\nInitializing fabric environment for %s.' % magenta(self.name)))

        # project_name:           example
        # project_name_prefix:    t-
        # user:                   t-example
        # project_path_name:      example

        # vhosts_path:            /var/www/vhosts/
        # vhost_path:             /var/www/vhosts/t-example/
        # current_instance_path:  /var/www/vhosts/t-example/current_instance/
        # previous_instance_path: /var/www/vhosts/t-example/previous_instance/
        # log_path:               /var/www/vhosts/t-example/log/
        # media_path:             /var/www/vhosts/t-example/media/
        # supervisor_path:        /var/www/vhosts/t-example/supervisor

        env.update({
            'cache_path': '/opt/pip_cache',
            'current_instance_path': os.path.join(vhost_path, 'current_instance'),
            'database_name': env.project_name,
            'environment': env.environment,
            'hosts': env.hosts,
            'log_path': os.path.join(vhost_path, 'log'),
            'media_path': os.path.join(vhost_path, 'media'),
            'previous_instance_path': os.path.join(vhost_path, 'previous_instance'),
            'vhost_path': vhost_path,
            'user': '%s%s' % (env.project_name_prefix, env.project_name),
            'compass_version': env.compass_version if 'compass_version' in env else None,
            'supervisor_path': os.path.join(vhost_path, 'supervisor'),
        })

        env.setdefault('project_path_name', env.project_name)


class RemoteTask(Task):
    """
    Base class for remote tasks
        - updates fabric env for instance
        - handles logging
    """

    requirements = [
        'vhost_path',
        'project_name',
    ]

    def __call__(self, *args, **kwargs):
        """ Task implementation - called from self.run() """

        raise NotImplementedError

    def log(self, success):
        utils.instance.log(success, task_name=self.name, stamp=self.stamp, log_path=env.log_path)

    def run(self, *args, **kwargs):
        """ Hide output, update fabric env, run task """

        # hide fabric output
        if 'debug' in args:
            hidden_groups = ('running',)
        else:
            hidden_groups = ('running', 'stdout')

        with settings(hide(*hidden_groups), warn_only=True):

            # check if HOST task was run before this task
            if not hasattr(env, 'current_instance_path'):
                message = str.join(' ', [
                    red('\nRun a HOST task before running this remote task (e.g. `fab staging deploy`).\n'),
                    'Use `fab -l` to see a list of all available tasks.\n',
                    'Use `fab -d %s` to see this task\'s details.\n' % self.name,
                ])
                abort(message)

            # load current instance unless task already provided something else
            if not hasattr(self, 'stamp'):
                self.stamp = utils.instance.get_instance_stamp(env.current_instance_path)

            # check if all required HOST settings are present in fabric environment
            [require(r) for r in self.requirements]

            # update fabric environment for instance settings
            # instance_path is the path of current instance; it's not the symbolic link
            instance_path = utils.commands.read_link(env.current_instance_path)

            full_project_name = '%s%s' % (env.project_name_prefix, env.project_name)

            # instance_stamp:       [sha1]

            # instance_path:        /var/www/vhosts/t-example/[sha1]/
            # backup_path:          /var/www/vhosts/t-example/[sha1]/backup/
            # source_path:          /var/www/vhosts/t-example/[sha1]/t-example/
            # project_path:         /var/www/vhosts/t-example/[sha1]/t-example/
            # project_project_path: /var/www/vhosts/t-example/[sha1]/t-example/example/
            # virtualenv_path:      /var/www/vhosts/t-example/[sha1]/env/

            env.update({
                'backup_path': os.path.join(instance_path, 'backup'),
                'instance_stamp': self.stamp,
                'instance_path': instance_path,
                'source_path': os.path.join(instance_path, full_project_name),
                'project_path': os.path.join(instance_path, full_project_name),
                'project_project_path': os.path.join(instance_path, full_project_name, env.project_path_name),
                'virtualenv_path': os.path.join(instance_path, 'env'),
            })

            # finally, run the task implementation!
            self(*args, **kwargs)


class Deployment(RemoteTask):
    """
    REMO - Deploy new instance

        Usage:

        # deployment using current git HEAD
        $ fab staging deploy
    """

    name = 'deploy'

    def run(self, *args, **kwargs):
        """
        Load instance from CLI kwargs

            deploy by HEAD for current branch
        """

        with settings(hide('warnings', 'running', 'stdout', 'stderr'), warn_only=True):

            # check if remote stamp exists in local repo
            current_instance = utils.commands.read_link(env.current_instance_path)
            remote_stamp = utils.instance.get_instance_stamp(current_instance)

            # first deploy to remote
            if '/' in remote_stamp:
                print(green('\nFirst deploy to remote.'))

            # deployed commit is not in your local repository
            elif remote_stamp and not utils.commands.remote_stamp_in_local_repo(remote_stamp):
                print(red('\nWarning: deployed commit is not in your local repository.'))

            # show changed files with `diff` command
            else:
                Diff().run()

            # ask to deploy
            self.stamp = utils.source.get_head()
            _args = (utils.source.get_branch_name(), self.stamp)

            question = '\nDeploy branch %s at commit %s?' % _args

            if not 'non_interactive' in args:
                if not confirm(yellow(question)):
                    abort(red('Aborted deployment. Run `fab -d %s` for options.' % self.name))

        super(Deployment, self).run(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        use_force = 'force' in args
        skip_syncdb = 'skip_syncdb' in args
        use_wheel = 'use_wheel' in args

        # check if deploy is possible
        if not use_force:
            if self.stamp == utils.instance.get_instance_stamp(env.current_instance_path):
                abort(red('Deploy aborted because %s is already the current instance.' % self.stamp))
            if self.stamp == utils.instance.get_instance_stamp(env.previous_instance_path):
                abort(red('Deploy aborted because %s is the previous instance. Use rollback task instead.' % self.stamp))
            if exists(env.instance_path):
                abort(red('Deploy aborted because instance %s has already been deployed.' % self.stamp))

        # Parse optional 'pause' argument, can be given like this:
        # fab staging deploy:pause=before_migrate
        pause_at = kwargs['pause'].split(',') if ('pause' in kwargs) else []

        website = WebsiteDeployment(
            vhost_path=env.vhost_path,
            project_name=env.project_name,
            project_name_prefix=env.project_name_prefix,
            project_settings_directory=env.project_path_name,
            stamp=self.stamp,
            pause_at=pause_at,
            use_wheel=use_wheel,
            skip_syncdb=skip_syncdb,
            restart_services=env.get('restart_services', None),
            task_args=args,
            task_kwargs=kwargs,
        )
        website.deploy()


class RemoveOldInstances(RemoteTask):
    """ REMO - Remove old instances """
    name = 'remove_old_instances'

    def __call__(self, *args, **kwargs):
        utils.instance.prune_obsolete_instances(env.vhost_path)


class Rollback(RemoteTask):
    """ REMO - Rollback current instance to previous instance """

    name = 'rollback'

    def __call__(self, *args, **kwargs):

        # check if rollback is possible
        if not exists(env.previous_instance_path):
            abort(red('No rollback possible. No previous instance found to rollback to.'))
        if not exists(os.path.join(env.backup_path, 'db_backup_start.sql')):
            abort(red('Could not find backupfile to restore database with.'))

        # start rollback
        is_website_running = True
        try:
            print(green('\nStopping website'))
            commands.stop_supervisor_jobs(env.vhost_path)
            is_website_running = False

            print(green('\nRestoring database to start of this instance.'))
            utils.instance.restore_database(
                os.path.join(env.backup_path, 'db_backup_start.sql')
            )

            print(green('\nRemoving this instance and set previous to current.'))
            utils.instance.rollback(env.vhost_path)

            print(green('\nStarting website.'))
            commands.start_supervisor_jobs(env.vhost_path)
            is_website_running = True

            print(green('\nRemoving this instance from filesystem.'))
            utils.commands.delete(env.instance_path)

            self.log(success=True)

        except Exception as e:
            if not is_website_running:
                commands.start_supervisor_jobs(env.vhost_path)

            self.log(success=False)
            abort(red('Rollback failed: %s ' % e.message))


class Status(RemoteTask):
    """ REMO - Show status information for remote host """

    name = 'status'

    def __call__(self, *args, **kwargs):

        print(green('\nCurrent instance:'))
        current_instance = utils.commands.read_link(env.current_instance_path)
        if current_instance != env.current_instance_path:
            print(current_instance)
        else:
            print(red('[none]'))

        print(green('\nPrevious instance:'))
        previous_instance = utils.commands.read_link(env.previous_instance_path)
        if previous_instance != env.previous_instance_path:
            print(previous_instance)
        else:
            print(red('[none]'))

        print(green('\nFabric log:'))
        if exists(os.path.join(env.log_path, 'fabric.log')):
            print(utils.commands.tail_file(os.path.join(env.log_path, 'fabric.log')))
        else:
            print(red('[empty]'))


class Size(RemoteTask):
    """ REMO - Show project size on remote host """

    name = 'size'

    def __call__(self, *args, **kwargs):

        print(green('\nCurrent size of entire project:'))
        print(utils.commands.get_folder_size(env.project_path))
        print(utils.commands.get_folder_size(env.media_path))


class Diff(RemoteTask):
    """ REMO - Show changed files with remote host

        Usage:

        $ fab staging diff

        # show full diff
        $ fab staging diff:full
    """

    name = 'diff'

    def __call__(self, *args, **kwargs):

        show_full_diff = False
        if 'full' in args:
            show_full_diff = True

        print(green('\nChanged files compared to remote host.'))
        print(utils.commands.get_changed_files(utils.source.get_head(), env.instance_stamp, show_full_diff))


class Media(RemoteTask):
    """ REMO - Download media files (as archive) """

    name = 'media'

    def __call__(self, *args, **kwargs):

        file_name = 'project_media.tar'
        cwd = os.getcwd()

        print(green('\nCompressing remote media folder.'))
        utils.commands.create_tarball(env.vhost_path, 'media', file_name)  # TODO: media_path?

        print(green('\nDownloading tarball.'))
        utils.commands.download_file(
            remote_path=os.path.join(env.vhost_path, file_name),
            local_path=os.path.join(cwd, file_name)
        )

        print(green('\nSaved media tarball to:'))
        print(os.path.join(cwd, file_name))


class Database(RemoteTask):
    """ REMO - Download database (as sqldump) """

    name = 'database'

    def __call__(self, output_filename=None):
        output_filename = backup_and_download_database(output_filename)

        print(green('\nSaved backup to:'))
        print(output_filename)


class RestoreDatabase(RemoteTask):
    """ REMO - Restore database """
    name = 'restore_database'

    def __call__(self):
        utils.instance.restore_database(
            os.path.join(env.backup_path, 'db_backup_start.sql')
        )


class Test(RemoteTask):
    """ REMO - Test task for testing pauses and hooks """

    name = 'test'

    def __call__(self, *args, **kwargs):

        """
        parse optional 'pause' argument, can be given like this:

        fab staging test:pause=test
        """
        pause_at = kwargs['pause'].split(',') if ('pause' in kwargs) else []

        # test pause
        if 'test' in pause_at:
            print(green('\nOpening remote shell - test.'))
            open_shell()

        # test hook
        if 'test' in env:
            env.test(env, *args, **kwargs)


class Restart(RemoteTask):
    """
    Restart the site using supervisor.
    - Also call 'after_restart' hook.
    """
    name = 'restart'

    requirements = [
        'project_name',
        'project_name_prefix',
    ]

    def __call__(self, *args, **kwargs):
        print(green('\nRestarting Website.'))

        restart_supervisor_jobs(env.vhost_path)

        if 'after_restart' in env:
            env.after_restart(env, *args, **kwargs)


class RestoreRemoteDatabase(RemoteTask):
    """ REMO - Restore remote database """
    name = 'restore_remote_database'

    def __call__(self, *args, **kwargs):
        settings = self.import_django_settings()

        self.check_database_engine(settings)
        local_backup_file = backup_and_download_database()

        print('Restoring database on local machine')
        database_name = settings.DATABASES['default']['NAME']
        database_user = settings.DATABASES['default']['USER']

        result = local('dropdb --if-exists %s' % database_name)

        if result.return_code != 0:
            print 'Could not remove local database'
        else:
            local('createdb %s --owner=%s --encoding=utf8' % (database_name, database_user))
            local('psql -d %s -f %s' % (database_name, local_backup_file))
            local('rm %s' % local_backup_file)

    def import_django_settings(self):
        sys.path.append(os.getcwd())

        django.project(env.project_path_name)
        from django.conf import settings

        return settings

    def check_database_engine(self, settings):
        engine = settings.DATABASES['default']['ENGINE']

        if engine != 'django.db.backends.postgresql_psycopg2':
            raise Exception('Only supports postgres database')


class InstallWheels(Task):
    name = 'install_wheels'

    def __init__(self, *args, **kwargs):
        self.skip_packages = kwargs.pop('skip_packages', [])

        super(InstallWheels, self).__init__(*args, **kwargs)

    def run(self):
        website_user = env.user
        env.user = 'leukeleu'

        with settings(hide('warnings', 'running', 'stdout', 'stderr'), warn_only=True):
            # try sudo root now
            sudo('ls')

            temp_wheels_dir = "/tmp/%s" % uuid.uuid4().hex
            try:
                requirements_file = os.path.join(temp_wheels_dir, 'requirements.txt')

                # Build the wheel as website user
                with settings(sudo=website_user):
                    sudo('mkdir %s' % temp_wheels_dir, user=website_user)
                    put('requirements.txt', requirements_file, use_sudo=True)
                    sudo("pip wheel --wheel-dir=%s --process-dependency-links -r %s" % (temp_wheels_dir, requirements_file), user=website_user)

                # Copy wheel files, except wheels from skip_packages option
                wheel_files = ls(os.path.join(temp_wheels_dir, '*.whl'))
                for wheel_file in wheel_files:
                    wheel_base_name = os.path.basename(wheel_file)
                    if self.must_include_file(wheel_base_name):
                        if not exists(os.path.join('/opt/wheels/', wheel_base_name)):
                            print wheel_base_name
                            sudo('cp %s /opt/wheels' % os.path.join(temp_wheels_dir, wheel_file))
            finally:
                sudo("rm -rf %s" % temp_wheels_dir)

    def must_include_file(self, wheel_file):
        for skip_package in self.skip_packages:
            if wheel_file.startswith('%s-' % skip_package):
                return False
        else:
            return True

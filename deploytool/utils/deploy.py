import os

from fabric.api import env
from fabric.colors import green, yellow, red
from fabric.context_managers import show, settings
from fabric.contrib.files import exists
from fabric.operations import open_shell
from fabric.utils import abort

from . import commands
from . import source
from . import instance


class WebsiteDeployment(object):
    """
    Deploy a site and make this deployment the current deployment. Also update the database and restart the site

    Steps:
    - Copy the files from git
    - Create virtualenv and install requirements
    - Collect static files
    - Update database
    - Restart site
    - Set current_instance link

    Also:
    - Copy django settings files
    - Link media folder

    Parameters:
    - vhost_path:          site source; e.g. /var/www/vhosts/t-example/
    - project_name:        example
    - project_name_prefix: t-
    - stamp:               sha1 stamp of git checkin; normally this is the head of the repository
    """
    def __init__(self, vhost_path, project_name, project_name_prefix, project_settings_directory, stamp, pause_at, use_wheel, skip_syncdb, task_args, task_kwargs):
        self.vhost_path = vhost_path
        self.stamp = stamp
        self.pause_at = pause_at
        self.use_wheel = use_wheel
        self.skip_syncdb = skip_syncdb
        self.task_args = task_args
        self.task_kwargs = task_kwargs

        self.log_path = os.path.join(vhost_path, 'log')
        self.instance_path = self.get_instance_path()
        self.source_path = os.path.join(self.instance_path, '%s%s' % (project_name_prefix, project_name))
        self.virtualenv_path = os.path.join(self.instance_path, 'env')
        self.project_settings_path = os.path.join(self.source_path, project_settings_directory)
        self.backup_path = os.path.join(self.instance_path, 'backup')

        # Update env variables because they are used by hooks
        env.project_path = self.source_path
        env.virtualenv_path = self.virtualenv_path

    def deploy(self):
        try:
            self.create_folders()

            self.deploy_source()

            self.handle_compass()

            self.create_virtualenv()

            self.pip_install()

            self.install_gunicorn()

            self.copy_settings()

            self.create_media_folder_link()

            self.collect_static_files()
        except:
            self.rollback()

        if not self.skip_syncdb:
            self.update_database()

        self.handle_restart()

        self.log_success()

        instance.prune_obsolete_instances(self.vhost_path)

    def create_folders(self):
        print(green('\nCreating folders.'))

        folders_to_create = [
            self.instance_path,
            self.backup_path,
            self.source_path,
            self.virtualenv_path,
        ]

        for folder in folders_to_create:
            commands.create_folder(folder)

    def deploy_source(self):
        if 'before_deploy_source' in self.pause_at:
            print(green('\nOpening remote shell - before_deploy_source.'))

            open_shell()

        if 'before_deploy_source' in env:
            env.before_deploy_source(env, *self.task_args, **self.task_kwargs)

        print(green('\nDeploying source.'))

        source.transfer_source(upload_path=self.source_path, tree=self.stamp)

    def handle_compass(self):
        if env.compass_version:
            if 'before_compass_compile' in self.pause_at:
                print(green('\nOpening remote shell - before_compass_compile.'))

                open_shell()

            if 'before_compass_compile' in env:
                env.before_compass_compile(env, *self.task_args, **self.task_kwargs)

            print(green('\nCompiling compass project and upload static files.'))

            source.compass_compile(upload_path=self.source_path, tree=self.stamp, compass_version=env.compass_version)

    def create_virtualenv(self):
        if 'before_create_virtualenv' in self.pause_at:
            print(green('\nOpening remote shell - before_create_virtualenv.'))

            open_shell()

        if 'before_create_virtualenv' in env:
            env.before_create_virtualenv(env, *self.task_args, **self.task_kwargs)

        print(green('\nCreating virtual environment.'))

        instance.create_virtualenv(self.virtualenv_path)

    def pip_install(self):
        if 'before_pip_install' in self.pause_at:
            print(green('\nOpening remote shell - before_pip_install.'))

            open_shell()

        if 'before_pip_install' in env:
            env.before_pip_install(env, *self.task_args, **self.task_kwargs)

        if exists(os.path.join(self.source_path, '*.pth')):
            print(green('\nCopying .pth files.'))

            commands.copy(
                from_path=os.path.join(self.source_path, '*.pth'),
                to_path='%s/lib/python%s/site-packages' % (self.virtualenv_path, commands.get_python_version())
            )

        print(green('\nPip installing requirements.'))

        # TODO: use requirements_path instead of project_path?

        instance.pip_install_requirements(
            self.virtualenv_path,
            self.source_path,
            env.cache_path,
            self.log_path,
            use_wheel=self.use_wheel
        )

        if 'after_pip_install' in self.pause_at:
            print(green('\nOpening remote shell - after_pip_install.'))

            open_shell()

        if 'after_pip_install' in env:
            env.after_pip_install(env, *self.task_args, **self.task_kwargs)

    def install_gunicorn(self):
        instance.pip_install_package(
            self.virtualenv_path,
            'gunicorn',
            '17.5',
            env.cache_path,
            self.log_path,
        )

    def copy_settings(self):
        print(green('\nCopying settings.py.'))

        commands.copy(
            from_path=os.path.join(self.vhost_path, 'settings.py'),
            to_path=os.path.join(self.project_settings_path, 'settings.py')
        )

        site_settings_file = os.path.join(self.vhost_path, 'site_settings.py')

        if commands.exists(site_settings_file):
            commands.copy(
                from_path=site_settings_file,
                to_path=os.path.join(self.project_settings_path, 'site_settings.py')
            )

    def create_media_folder_link(self):
        print(green('\nLinking media folder.'))

        commands.create_symbolic_link(
            real_path=os.path.join(self.vhost_path, 'media'),
            symbolic_path=os.path.join(self.source_path, 'media')
        )

    def collect_static_files(self):
        print(green('\nCollecting static files.'))

        commands.collect_static(self.virtualenv_path, self.source_path)

    def rollback(self):
        instance.log(success=False, task_name='deploy', stamp=self.stamp, log_path=self.log_path)

        print(yellow('\nRemoving this instance from filesystem.'))

        commands.delete(self.instance_path)

        abort(red('Deploy failed and was rolled back.'))

    def update_database(self):
        try:
            self.backup_db_at_start()

            with settings(show('stdout')):
                self.syncdb()
                self.migrate()

            # todo: must the 'backup at end' moved to after the except?
            self.backup_db_at_end()
        except:
            self.restore_db_at_start()

            self.rollback()

    def backup_db_at_start(self):
        print(green('\nBacking up database at start.'))

        instance.backup_database(
            os.path.join(self.backup_path, 'db_backup_start.sql')
        )

    def backup_db_at_end(self):
        print(green('\nBacking up database at end.'))

        instance.backup_database(
            os.path.join(self.backup_path, 'db_backup_end.sql')
        )

    def restore_db_at_start(self):
        backup_file = os.path.join(self.backup_path, 'db_backup_start.sql')

        if exists(backup_file):
            print(yellow('\nRestoring database.'))

            instance.restore_database(backup_file)

    def syncdb(self):
        if 'before_syncdb' in self.pause_at:
            print(green('\nOpening remote shell - before_syncdb.'))

            open_shell()

        if 'before_syncdb' in env:
            env.before_syncdb(env, *self.task_args, **self.task_kwargs)

        print(green('\nSyncing database.'))

        commands.django_manage(self.virtualenv_path, self.source_path, 'syncdb')

        print('')

    def migrate(self):
        if 'before_migrate' in self.pause_at:
            print(green('\nOpening remote shell - before_migrate.'))

            open_shell()

        if 'before_migrate' in env:
            env.before_migrate(env, *self.task_args, **self.task_kwargs)

        print(green('\nMigrating database.'))

        commands.django_manage(self.virtualenv_path, self.source_path, 'migrate')

        print('')

    def handle_restart(self):
        self.handle_before_restart()

        self.update_instance_symlinks()

        self.restart_supervisor()

        self.handle_after_restart()

    def handle_before_restart(self):
        if 'before_restart' in self.pause_at:
            print(green('\nOpening remote shell - before_restart.'))

            open_shell()

        if 'before_restart' in env:
            env.before_restart(env, *self.task_args, **self.task_kwargs)

    def update_instance_symlinks(self):
        instance.set_current_instance(self.vhost_path, self.instance_path)

    def restart_supervisor(self):
        print(green('\nRestarting Website.'))
        commands.restart_supervisor_jobs(self.vhost_path)

    def handle_after_restart(self):
        if 'after_restart' in self.pause_at:
            print(green('\nOpening remote shell - after_restart.'))

            open_shell()

        if 'after_restart' in env:
            env.after_restart(env, *self.task_args, **self.task_kwargs)

    def log_success(self):
        instance.log(success=True, task_name='deploy', stamp=self.stamp, log_path=self.log_path)

    def get_instance_path(self):
        instance_path = os.path.join(self.vhost_path, self.stamp)

        if not exists(instance_path):
            return instance_path
        else:
            index = 1
            while True:
                candidate_path = '%s_%d' % (instance_path, index)

                if not exists(candidate_path):
                    return candidate_path

                index += 1

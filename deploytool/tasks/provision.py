import os
from datetime import datetime

from fabric.api import *
from fabric.colors import *
from fabric.contrib.files import *
from fabric.contrib.console import confirm
from fabric.operations import require
from fabric.tasks import Task

import deploytool
from deploytool.db import get_database_operations


class ProvisioningTask(Task):
    """
    Base class for provisioning tasks

        - checks requirements in fabric environment
        - sets default level of commandline output verbosity
        - uses provisioning_user to connect
        - uses sudo for remote commands
        - calls task implementation
    """

    def run(self):

        # check if all required project and host settings are present in fabric environment
        [require(r) for r in self.requirements]

        with settings(hide('running', 'stdout'), warn_only=True):

            # connect with provision user (who must have sudo rights on host)
            # note that this user differs from local (e.g 'nick') or project user (e.g. 's-myproject')
            # make sure local user either knows remote password, or has its local public key on remote end
            print(green('\nConnecting with user %s' % magenta(env.provisioning_user)))
            env.update({'user': env.provisioning_user})

            # ask for sudo session up front
            sudo('ls')

            # call task implementation in subclass
            self()

    def __call__(self):

        raise NotImplementedError


class Setup(ProvisioningTask):
    """
    PROV - Provision a new project

        [1] create user
        [2] create folders
        [3] copy files
        [4] create files
        [5] create database + user
        [6] .htpasswd (optional)
        [7] setup vhosts
        [8] restart webservers (optional)

        Note that this task is intentionally not reversible.
        Any conflicts need to be fixed manually. Some tips:

            # remove a remote user (including home dir and mail spool)
            $ /usr/sbin/userdel -rf the_users_name

            # remove all remote project files
            $ rm -rf /var/www/vhosts/the_project_full_name
            $ rm /etc/httpd/conf.d/vhosts-the_projects_full_name.conf
            $ rm /etc/nginx/conf.d/vhosts-the_projects_full_name.conf

            Use a DBMS (i.e. Sequel Pro) for managing databases and its users.
    """

    name = 'setup'
    requirements = [
        'admin_email',
        'cache_path',
        'current_instance_path',
        'database_name',
        'environment',
        'log_path',
        'local_user',
        'media_path',
        'project_name',
        'project_name_prefix',
        'vhosts_path',
        'vhost_path',
        'provisioning_user',
        'real_fabfile',
        'scripts_path',
        'website_name',
    ]

    def __call__(self):

        # project user (e.g. `s-myproject`)
        project_user = '%s%s' % (env.project_name_prefix, env.project_name)

        # locations of local folders (based on running fabfile.py) needed for remote file transfers
        local_scripts_path = os.path.join(os.path.dirname(deploytool.__file__), 'scripts')
        local_templates_path = os.path.join(os.path.dirname(deploytool.__file__), 'templates')

        # locations of remote paths - TODO: make these configable
        user_home_path = os.path.join('/', 'home', project_user)
        user_ssh_path = os.path.join(user_home_path, '.ssh')
        auth_keys_file = os.path.join(user_ssh_path, 'authorized_keys')
        htpasswd_path = os.path.join(env.vhost_path, 'htpasswd')
        nginx_conf_path = os.path.join('/', 'etc', 'nginx', 'conf.d')
        apache_conf_path = self.get_apache_conf_path()
        apache_daemon = self.get_apache_daemon()
        python_version = self.get_python_version()

        # check if vhosts path exists
        if not exists(env.vhosts_path, use_sudo=True):
            abort(red('vhosts path not found at: %s' % env.vhosts_path))

        # check for existing vhost path, and abort if found
        if exists(env.vhost_path, use_sudo=True):
            abort(red('vhost path already exists at: %s' % env.vhost_path))

        # prompt for start
        question = '\nStart provisioning of `%s` on `%s`?' % (env.project_name, env.environment)
        if not confirm(yellow(question)):
            abort(red('\nProvisioning cancelled.'))

        # [1] create new project_user
        print(green('\nCreating project user `%s`' % project_user))
        user_exists = bool(run('cat /etc/passwd').find(project_user + ':') > 0)

        if user_exists:
            # user already exists, ask if this user is available for reuse
            if not confirm(yellow('User `%s` already exist. Continue anyway?' % project_user)):
                abort(red('Aborted by user, because remote user `%s` is not available.' % project_user))
        else:
            # add new user/password
            # Option -m makes sure a homedirectory is created.
            sudo('useradd -m %s' % project_user)
            with(show('stdout')):
                sudo('passwd %s' % project_user)
                print('')

        # create .ssh in home folder
        if not exists(user_ssh_path, use_sudo=True):
            sudo('mkdir %s' % user_ssh_path)

        # create authorized_keys
        if not exists(auth_keys_file, use_sudo=True):
            sudo('touch %s' % auth_keys_file)

        # setup ownership & access
        sudo('chmod -R 700 %s' % user_ssh_path)
        sudo('chown -R %s:%s %s' % (project_user, project_user, user_home_path))

        # [2] setup project folders
        print(green('\nCreating folders'))
        folders_to_create = [
            env.vhost_path,
            env.cache_path,
            env.log_path,
            env.media_path,
            env.scripts_path,
        ]

        for folder in folders_to_create:
            sudo('mkdir %s' % folder)

        # [3] copy files
        print(green('\nCopying script files'))
        files_to_copy = os.listdir(local_scripts_path)

        for file_name in files_to_copy:
            put(
                local_path=os.path.join(local_scripts_path, file_name),
                remote_path=os.path.join(env.scripts_path, file_name),
                use_sudo=True
            )

        database_operations = get_database_operations(env.database_engine)

        # ask user input for template based file creation
        # TODO: security issue for password prompt
        print(yellow('\nProvide info for file creation:'))
        database_name = prompt('Database name: ', default=project_user)
        database_user = prompt('Database username (max 16 characters for MySQL): ', default=project_user)

        if database_operations.needs_password:
            database_pass = prompt('Database password: ', validate=self._validate_password)
        else:
            database_pass = ''

        files_to_create = [
            {'template': 'settings_py.txt', 'file': 'settings.py', },
            {'template': 'credentials_py.txt', 'file': 'scripts/credentials.py', },
            {'template': 'django_wsgi.txt', 'file': 'django.wsgi', },
        ]

        context = {
            'project_name': env.project_name,
            'current_instance_path': env.current_instance_path,
            'cache_path': env.cache_path,
            'database_name': database_name,
            'username': database_user,
            'password': database_pass,
            'python_version': python_version,
            'project_path_name': env.project_path_name,
            'engine': database_operations.engine_name,
        }

        # [4] create files from templates (using fabric env and user input)
        print(green('\nCreating project files'))
        for file_to_create in files_to_create:
            upload_template(
                filename=os.path.join(local_templates_path, file_to_create['template']),
                destination=os.path.join(env.vhost_path, file_to_create['file']),
                context=context,
                use_sudo=True
            )

        # [5] create new database + user with all schema privileges (uses database root user)
        print(green('\nCreating database `%s` with privileged db-user `%s`' % (
            database_name,
            project_user
        )))

        if database_operations.database_exists(database_name):
            if not confirm(yellow('Database `%s` already exists. Continue anyway?' % database_name)):
                abort(red('Aborted by user, because database `%s` already exists.' % database_name))

        # all is well, and user is ok should database already exist
        database_operations.create_database(database_name, database_user, database_pass)

        # [6] ask for optional setup of .htpasswd (used for staging environment)
        if confirm(yellow('\nSetup htpasswd for project?')):
            htusername = env.project_name
            htpasswd = '%s%s' % (env.project_name, datetime.now().year)
            sudo('mkdir %s' % htpasswd_path)

            with cd(htpasswd_path):
                sudo('htpasswd -bc .htpasswd %s %s' % (htusername, htpasswd))

        # [7] create webserver conf files
        print(green('\nCreating vhost conf files'))
        try:
            # grep vhosts => reverse list => awk top port #
            output = run('%s | %s | %s' % (
                'grep -hr "NameVirtualHost" %s' % apache_conf_path,
                'sort -r',
                'awk \'{if (NR==1) { print substr($2,3) }}\''
            ))
            new_port_nr = int(output) + 1
        except:
            new_port_nr = 8000

        print('Port %s will be used for this project' % magenta(new_port_nr))

        # check if htpasswd is used (some nginx vhost lines will be commented if it isn't)
        if not exists(htpasswd_path, use_sudo=True):
            use_htpasswd = '#'
        else:
            use_htpasswd = ''

        # assemble context for apache and nginx vhost conf files
        context = {
            'port_number': new_port_nr,
            'current_instance_path': env.current_instance_path,
            'website_name': env.website_name,
            'project_name': env.project_name,
            'project_name_prefix': env.project_name_prefix,
            'vhost_path': env.vhost_path,
            'log_path': env.log_path,
            'admin_email': env.admin_email,
            'project_user': project_user,
            'use_htpasswd': use_htpasswd,
        }

        # create the conf files from template and transfer them to remote server
        upload_template(
            filename=os.path.join(local_templates_path, 'apache_vhost.txt'),
            destination=os.path.join(apache_conf_path, 'vhosts-%s.conf' % project_user),
            context=context,
            use_sudo=True
        )
        upload_template(
            filename=os.path.join(local_templates_path, 'nginx_vhost.txt'),
            destination=os.path.join(nginx_conf_path, 'vhosts-%s.conf' % project_user),
            context=context,
            use_sudo=True
        )

        # chown project for project user
        print(green('\nChanging ownership of %s to `%s`' % (env.vhost_path, project_user)))
        sudo('chown -R %s:%s %s' % (project_user, project_user, env.vhost_path))

        # [8] prompt for webserver restart
        print(green('\nTesting webserver configuration'))
        with settings(show('stdout')):
            self.run_apache_configtest()
            sudo('/etc/init.d/nginx configtest')
            print('')

        if confirm(yellow('\nOK to restart webserver?')):
            with settings(show('stdout')):
                sudo('%s restart' % apache_daemon)
                sudo('/etc/init.d/nginx restart')
                print('')
        else:
            print(magenta('Website will be available when webservers are restarted.'))

    def _validate_password(self, password):
        """ Validator for input prompt when asking for password """

        min_length_required = 8

        if len(password.strip()) < min_length_required:
            raise Exception(red('Please enter a valid password of at least %s characters' % min_length_required))

        return password.strip()

    def get_apache_conf_path(self):
        """
        Get the apache conf path.
        The path is /etc/httpd/conf.d on Centos and /etc/apache2/conf.f on Ubuntu

        If no path is found, then abort.
        """
        apache_conf_path = self.find_first_existing_path(
            os.path.join('/', 'etc', 'httpd', 'conf.d'),
            os.path.join('/', 'etc', 'apache2', 'conf.d')
        )

        if apache_conf_path:
            return apache_conf_path
        else:
            abort(red('apache conf path not found'))

    def get_apache_daemon(self):
        """
        Get apache daemon.
        The daemon is /etc/init.d/httpd on Centos and /etc/init.d/apache2 on Ubuntu

        If no path is found, then abort.
        """
        apache_daemon = self.find_first_existing_path(
            os.path.join('/', 'etc', 'init.d', 'httpd'),
            os.path.join('/', 'etc', 'init.d', 'apache2')
        )

        if apache_daemon:
            return apache_daemon
        else:
            abort(red('apache daemon not found'))

    def find_first_existing_path(self, *paths):
        """
        Find the first path that exists. If no path is found, return None.
        """
        for path in paths:
            if exists(path):
                return path

        return None

    def get_python_version(self):
        """
        Return python version as <major>.<minor> string.
        E.g. '2.6'
        """
        command = "python -c \"import sys;print '%s.%s' % (sys.version_info.major, sys.version_info.minor)\""

        return run(command)

    def run_apache_configtest(self):
        """
        Return apache configtest using apachectl or apache daemon.
        """
        if run('which apachectl', quiet=True):
            sudo('apachectl configtest')
        else:
            sudo('%s configtest' % self.get_apache_daemon())


class Keys(ProvisioningTask):
    """
    PROV - Enable devs for project by managing SSH keys

        Transfers a selected user's public SSH key to remote user's authorized key.
        This regulates access for admins without having to divulge project passwords.
    """

    name = 'keys'
    requirements = [
        'local_user',
        'project_name',
        'project_name_prefix',
        'provisioning_user',
    ]

    def __call__(self):

        project_user = env.project_name_prefix + env.project_name
        local_ssh_path = os.path.join(os.environ['HOME'], '.ssh')
        local_ssh_files = os.listdir(local_ssh_path)
        local_key_files = [f for f in local_ssh_files if f[-4:] == '.pub']
        remote_auth_keys = os.path.join('/', 'home', project_user, '.ssh', 'authorized_keys')

        if not local_key_files:
            abort(red('No public keys found in %s' % local_ssh_path))
        elif not exists(remote_auth_keys, use_sudo=True):
            abort(red('No authorized_keys found at %s' % remote_auth_keys))

        print(green('\nShowing local public keys in %s:' % local_ssh_path))
        for file in local_key_files:
            index = local_key_files.index(file)
            key_file = os.path.join(local_ssh_path, local_key_files[index])

            if self._is_key_authorized(remote_auth_keys, self._read_key(key_file)):
                print('[%s] %s (already enabled)' % (red(index), file))
            else:
                print('[%s] %s' % (green(index), file))

        print('\n[s] show all remote authorized keys')
        print('[a] enable all local keys')
        print('[d] disable all remote keys')
        selection = prompt(yellow('\nSelect option:'), default='s')

        if selection == 's':
            print(green('\nRemote authorized keys:'))
            print(sudo('cat %s' % remote_auth_keys) or red('[empty]'))

        elif selection == 'a':
            for file in local_key_files:
                # grab key from selection (if multiple) or default (if single)
                key_file = os.path.join(local_ssh_path, file)
                key_to_transfer = self._read_key(key_file)
                self._transfer_key(remote_auth_keys, key_to_transfer)

        elif selection == 'd':
            print(green('\nDisabled all keys'))
            sudo('rm -f %s' % remote_auth_keys)
            sudo('touch %s' % remote_auth_keys)
            sudo('chmod -R 700 %s' % remote_auth_keys)
            sudo('chown %s:%s %s' % (project_user, project_user, remote_auth_keys))

        else:
            try:
                key_file = os.path.join(local_ssh_path, local_key_files[int(selection)])
                key_to_transfer = self._read_key(key_file)
                self._transfer_key(remote_auth_keys, key_to_transfer)
            except:
                abort(red('Invalid selection'))

    def _transfer_key(self, remote_auth_keys, key_to_transfer):
        """ Appends key to supplied authorized_keys file """

        if not self._is_key_authorized(remote_auth_keys, key_to_transfer):
            print(green('\nTransferring key'))
            print(key_to_transfer)
            append(remote_auth_keys, key_to_transfer, use_sudo=True)

    def _read_key(self, key_file):
        """ Returns the content of a (public) SSH key-file """

        return '%s' % local('cat %s' % key_file, capture=True).strip()

    def _is_key_authorized(self, auth_keys_file, public_key):
        """ Checks if key is present in supplied authorized_keys file """

        authorized_keys = sudo('cat %s' % auth_keys_file)
        return bool(public_key in authorized_keys.split('\r\n'))

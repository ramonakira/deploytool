from datetime import datetime
import os

from fabric.api import *
from fabric.colors import *
from fabric.contrib.files import *
from fabric.contrib.console import confirm
from fabric.operations import require
from fabric.tasks import Task

from deploytool.db import get_database_operations
from deploytool.utils.commands import upload_jinja_template, get_local_templates_path, get_template_paths


HAPROXY_CONF_DIR = '/etc/haproxy/'
HAPROXY_CONF_FILE = os.path.join(HAPROXY_CONF_DIR, 'haproxy.cfg')
NGINX_CONFD_PATH = '/etc/nginx/conf.d'
PASSWD_FILE = '/etc/passwd'
SUPERVISOR_CONFD_PATH = '/etc/supervisor/conf.d'
NGINX_CONFIGTEST = '/etc/init.d/nginx configtest'
HAPROXY_INITD = '/etc/init.d/haproxy'
NGINX_INITD = '/etc/init.d/nginx'


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
        [6] basic auth (optional)
        [7] setup vhosts
        [8] restart webservers (optional)

        Note that this task is intentionally not reversible.
        Any conflicts need to be fixed manually. Some tips:

            # remove a remote user (including home dir and mail spool)
            $ /usr/sbin/userdel -rf the_users_name

            # remove all remote project files
            $ rm -rf /var/www/vhosts/the_project_full_name
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

        # locations of remote paths - TODO: make these configable
        user_home_path = os.path.join('/', 'home', project_user)
        user_ssh_path = os.path.join(user_home_path, '.ssh')
        auth_keys_file = os.path.join(user_ssh_path, 'authorized_keys')
        nginx_conf_path = NGINX_CONFD_PATH
        haproxy_conf_path = HAPROXY_CONF_FILE
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
        user_exists = bool(run('cat %s' % PASSWD_FILE).find(project_user + ':') > 0)

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
            {'template': 'credentials_json.txt', 'file': 'credentials.json', },
        ]

        context = {
            'project_name': env.project_name,
            'project_user': project_user,
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
            template_filename = file_to_create['template']

            upload_jinja_template(
                filenames=['override_%s' % template_filename, template_filename],
                destination=os.path.join(env.vhost_path, file_to_create['file']),
                context=context,
                template_paths=get_template_paths()
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

        # [6] basic auth (optional)
        if confirm(yellow('\nSetup htpasswd for project?')):
            htusername = env.project_name
            htpasswd = '%s%s' % (env.project_name, datetime.now().year)
        else:
            htusername = ''
            htpasswd = ''

        # [7] create webserver conf files
        print(green('\nCreating vhost conf files'))
        try:
            output = run('%s | %s | %s | %s' % (
                'grep "server django 127.0.0.1:" %s' % haproxy_conf_path,
                r"sed 's/.*server django 127\.0\.0\.1\:\([0-9]*\).*/\1/'",
                'sort -nr',
                'head -1'
            ))
            django_port_nr = int(output) + 1
        except:
            django_port_nr = 8000

        print('Django port %s will be used for this project' % magenta(django_port_nr))

        try:
            output = run('%s | %s | %s | %s' % (
                'grep "server static 127.0.0.1:" %s' % haproxy_conf_path,
                r"sed 's/.*server static 127\.0\.0\.1\:\([0-9]*\).*/\1/'",
                'sort -nr',
                'head -1'
            ))
            nginx_port_nr = int(output) + 1
        except:
            nginx_port_nr = 9000

        print('Nginx port %s will be used for this project' % magenta(nginx_port_nr))

        # assemble context for conf files
        context = {
            'django_port': django_port_nr,
            'nginx_port': nginx_port_nr,
            'current_instance_path': env.current_instance_path,
            'website_name': env.website_name,
            'project_name': env.project_name,
            'project_name_prefix': env.project_name_prefix,
            'vhost_path': env.vhost_path,
            'log_path': env.log_path,
            'admin_email': env.admin_email,
            'project_user': project_user,
            'htusername': htusername,
            'htpasswd': htpasswd,
        }

        # create the conf files from template and transfer them to remote server
        upload_jinja_template(
            filenames=['override_supervisor_conf.txt', 'supervisor_conf.txt'],
            destination=os.path.join(SUPERVISOR_CONFD_PATH, '%s.conf' % project_user),
            context=context,
            template_paths=get_template_paths()
        )
        upload_jinja_template(
            filenames=['override_nginx_vhost.txt', 'nginx_vhost.txt'],
            destination=os.path.join(nginx_conf_path, 'vhosts-%s.conf' % project_user),
            context=context,
            template_paths=get_template_paths()
        )

        haproxy_backend_path = os.path.join(HAPROXY_CONF_DIR, 'backends')
        haproxy_backend_django_path = os.path.join(haproxy_backend_path, '%s_django' % project_user)
        sudo('mkdir -p %s' % haproxy_backend_django_path)

        upload_jinja_template(
            filenames=['override_haproxy_backend_django.txt', 'haproxy_backend_django.txt'],
            destination=os.path.join(haproxy_backend_django_path, 'default'),
            context=context,
            template_paths=get_template_paths()
        )

        haproxy_backend_static_path = os.path.join(haproxy_backend_path, '%s_static' % project_user)
        sudo('mkdir -p %s' % haproxy_backend_static_path)

        upload_jinja_template(
            filenames=['override_haproxy_backend_static', 'haproxy_backend_static.txt'],
            destination=os.path.join(haproxy_backend_static_path, 'default'),
            context=context,
            template_paths=get_template_paths()
        )

        haproxy_frontend_path = os.path.join(HAPROXY_CONF_DIR, 'frontends', 'all')
        haproxy_frontend_file_path = os.path.join(haproxy_frontend_path, project_user)
        sudo('mkdir -p %s' % haproxy_frontend_path)

        upload_jinja_template(
            filenames=['override_haproxy_frontend.txt', 'haproxy_frontend.txt'],
            destination=haproxy_frontend_file_path,
            context=context,
            template_paths=get_template_paths()
        )

        if htusername:
            upload_jinja_template(
                filenames=['override_haproxy_userlist.txt', 'haproxy_userlist.txt'],
                destination=os.path.join(HAPROXY_CONF_DIR, 'all', '%s%s' % (env.project_name_prefix, env.project_name)),
                context=context,
                template_paths=get_template_paths()
            )

        # chown project for project user
        print(green('\nChanging ownership of %s to `%s`' % (env.vhost_path, project_user)))
        sudo('chown -R %s:%s %s' % (project_user, project_user, env.vhost_path))

        # [8] prompt for webserver restart
        print(green('\nTesting webserver configuration'))
        with settings(show('stdout')):
            sudo(NGINX_CONFIGTEST)
            print('')

        if confirm(yellow('\nOK to restart webserver?')):
            with settings(show('stdout')):
                sudo('%s restart' % HAPROXY_INITD)
                sudo('%s restart' % NGINX_INITD)
                print('')
        else:
            print(magenta('Website will be available when webservers are restarted.'))

        # update supervisor
        sudo('supervisorctl update')

    def _validate_password(self, password):
        """ Validator for input prompt when asking for password """

        min_length_required = 8

        if len(password.strip()) < min_length_required:
            raise Exception(red('Please enter a valid password of at least %s characters' % min_length_required))

        return password.strip()

    def get_python_version(self):
        """
        Return python version as <major>.<minor> string.
        E.g. '2.6'
        """
        command = "python -c \"import sys;print '%s.%s' % (sys.version_info.major, sys.version_info.minor)\""

        return run(command)


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
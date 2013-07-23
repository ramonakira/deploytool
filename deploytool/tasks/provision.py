import os

from fabric.api import *
from fabric.colors import *
from fabric.contrib.files import *
from fabric.operations import require
from fabric.tasks import Task


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
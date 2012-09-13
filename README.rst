=================
Fabric Deployment
=================

Project application for deployment, provisioning and local tasks.


Remote requirements
===================
* Apache
* Cent OS
* gcc
* Nginx
* MySQL
* MySQL-python
* MySQL-devel
* OpenSSH
* Pip (0.8.1+)
* Python (2.6)
* python-devel
* sudo
* virtualenv (1.6+)


Local requirements
==================
* Fabric (1.2.2+)
* Git (1.6+)


Usage
=====
Install deploytool

::

    $ pip install deploytool


Prepare by having passwords at hand for these users:

* provisioning user (ssh, sudo)
* project user (deployment tasks)
* MySQL root user (database provisioning)
* MySQL project user (deployment tasks)
* Django admin user (site admin access)

Provision & deploy the project:

* Update fabfile.py with correct settings
* Run setup ('fab staging setup')
* Manage access ('fab staging keys')
* First deploy ('fab staging deploy')


Pausing
-------

The deploy can be paused at will at several predefined moments.
If you pause the deploy, you get thrown into a (slightly crippled) shell session on the remote server.
When you `exit` from the remote, the deploy will continue where it left off.

::

    $ fab staging deploy:pause={pause_moment}

Where {pause_moment} can be one of:

* before_deploy_source
* before_create_virtualenv
* before_pip_install
* after_pip_install
* before_syncdb
* before_migrate
* before_restart
* after_restart


Hooks
-----

Hooks are functions that can be run at predefined moments during the deploy.
Hooks can be attached to the deploy-flow of an instance like this:

::

    def before_syncdb(env, *args, **kwargs):
        # do something useful before syncing the database
        ...


    staging_items = {
        'website_name': 'subdomain.example.com',
        'project_name_prefix': 's-',
        'environment': 'staging',
        'before_syncdb': before_syncdb,
    }.items()


The available hooks are:

* before_deploy_source
* before_create_virtualenv
* before_pip_install
* after_pip_install
* before_syncdb
* before_migrate
* before_restart
* after_restart


Examples
========

::

    # list all available tasks
    $ fab list

    # show detailed information for task
    $ fab -d TASKNAME

    # execute task with parameters
    $ fab TASKNAME:ARG=VALUE

    # example: deploy current local commit to staging server
    $ fab staging deploy

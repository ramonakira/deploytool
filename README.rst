=================
Fabric Deployment
=================

Project application for deployment, provisioning and local tasks.


Remote requirements:
====================
* Apache
* CentOS
* gcc
* Nginx
* MySQL
* MySQL-python
* MySQL-devel
* OpenSSH
* Pip (1.1+)
* Python (2.6)
* python-devel
* sudo
* virtualenv (1.6+)


Local requirements:
===================
* Fabric (1.2.2+)
* Git (1.6+)


Usage:
======
Add deploytool to your Django project:

::

    $ pip install deploytool

Add a fabfile.py in the root folder of your Django project. An example can be found here:

`https://github.com/leukeleu/deploytool <https://github.com/leukeleu/deploytool>`_

Prepare by having passwords at hand for these users:

* Remote provisioning user (ssh, sudo)
* Remote MySQL root user (for database provisioning)

Provision & deploy the project:

* Run setup ('fab staging setup')
* Manage access ('fab staging keys')
* First deploy ('fab staging deploy')


Examples:
=========

::

    # list all available tasks
    $ fab list

    # show detailed information for task
    $ fab -d TASKNAME

    # execute task with parameters
    $ fab TASKNAME:ARG=VALUE

    # example: deploy latest version of local current branch to staging server
    $ fab staging deploy


Deployed Folder structure:
==========================

::

    /var/www/vhosts/                                               <- vhosts_path
        /s-myproject                                               <- vhost_path = {project_name_prefix}{project_name}
            django.wsgi
            settings.py                                               is copied to project_project_path/settings.py on every deploy
            /log
            /htpasswd                                                 optional
            /cache
            /media                                                 <- media_path
            /12a533d3f2...                                            the previous instance
            /previous_instance -> 12a533d3f2...                    <- previous_instance_path
            /2c27c98fe1...                                            the current instance
            /current_instance -> 2c27c98fe1...                     <- current_instance_path
                /env                                               <- virtualenv_path

                /myproject                                         <- project_path / requirements_path
                    manage.py ('changed')
                    requirements.txt
                    requirements.pth
                    /myproject                                     <- project_project_path
                        settings.py (changed)
                        urls.py
                        wsgi.py (changed)
                    /media -> /var/www/vhosts/s-myproject/media       is symlinked to media_path on every deploy

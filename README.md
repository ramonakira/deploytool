## Fabric Deployment

Project application for deployment and local tasks.


### Remote requirements

* Ubuntu
* Nginx
* Postgresql
* OpenSSH
* Pip (6+)
* Python (2.7)
* virtualenv (12+)


### Local requirements

* Fabric (1.2.2+)
* Git (1.6+)


### Usage

Install deploytool

    $ pip install deploytool


Add a fabfile.py in the root folder of your Django project. An example can be found here:

`https://github.com/leukeleu/deploytool <https://github.com/leukeleu/deploytool>`

Deploy the project:

* Manage access ('fab staging keys')
* First deploy ('fab staging deploy')


#### Pausing

The deploy can be paused at will at several predefined moments.
If you pause the deploy, you get thrown into a (slightly crippled) shell session on the remote server.
When you `exit` from the remote, the deploy will continue where it left off.

    $ fab staging deploy:pause={pause_moment}

Where {pause_moment} can be one of:

* before_deploy_source
* before_compass_compile
* before_create_virtualenv
* before_pip_install
* after_pip_install
* before_syncdb
* before_migrate
* before_restart
* after_restart
* test


#### Deploying without user input


A deploy can also be performed without the 'Deploy branch ... at ...? [Y/n]' prompt, like this:

    $ fab staging deploy:non_interactive


#### Hooks

Hooks are functions that can be run at predefined moments during the deploy.
Hooks can be attached to the deploy-flow of an instance like this:


    def before_syncdb(env, *args, **kwargs):
        # do something useful before syncing the database
        ...


    settings.update(
        ...
        before_syncdb=before_syncdb,
    )

The available hooks are:

* before_deploy_source
* before_compass_compile
* before_create_virtualenv
* before_pip_install
* after_pip_install
* before_syncdb
* before_migrate
* before_restart
* after_restart
* test


#### Compass compiling

When you set a `compass_version` number in your settings. The deploy task will compile your compass project locally, upload the locally generated root static dir to the remote. Remember that your compass config must compile your css to the root static dir of your django project. With this setting you can ignore your generated css files in your repository.

##### Examples

    # list all available tasks
    $ fab list

    # show detailed information for task
    $ fab -d TASKNAME

    # execute task with parameters
    $ fab TASKNAME:ARG=VALUE

    # example: deploy current local commit to staging server
    $ fab staging deploy


#### Deployed Folder structure

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

#### Use wheels

You can deploy faster using [Wheel](http://wheel.readthedocs.org) files.

##### Install wheels

Create wheel files on the server using the ``install_wheels`` command.

Add the ``install_wheels`` command to the fabfile:

  from deploytool import tasks
  install_wheels = tasks.remote.InstallWheels()

Call install_wheels command:

  $ fab live install_wheels

This will install the wheel files in the ``/opt/wheels`` directory.

You can skip packages with the ``skip_packages`` parameter in your fabfile:

    install_wheels = tasks.remote.InstallWheels(skip_packages=['Django'])

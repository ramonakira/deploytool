from fabric.colors import yellow
from fabric.operations import prompt, sudo, run, local


class DatabaseOperations(object):
    needs_password = True
    engine_name = 'mysql'

    def database_exists(self, database_name):
        output = self.root_execute(
            "SHOW DATABASES LIKE \'%s\'" % database_name,
            '--skip-column-names'
        )
        return bool(output.strip().lower() == database_name.lower())

    def create_database(self, database_name, owner, password):
        self.root_execute(r"CREATE DATABASE IF NOT EXISTS \\`%s\\` CHARACTER SET utf8 COLLATE utf8_general_ci" % database_name)

        self.root_execute(
            r"GRANT ALL PRIVILEGES ON \\`%s\\`.* TO '%s'@'localhost' IDENTIFIED BY '%s' WITH GRANT OPTION" % (
                database_name,
                owner,
                password
            )
        )
        self.root_execute('FLUSH PRIVILEGES')

    def backup_database(self, database_name, username, password, file_path):
        command = 'mysqldump --user=\'%s\' --password=\'%s\' \'%s\' > %s' % (
            username,
            password.replace("'", "\\'"),
            database_name,
            file_path
        )
        run(command)

    def restore_database(self, database_name, username, password, file_path, run_command=run):
        def drop_database():
            run_command(
                'mysqladmin -f --user="%s" --password="%s" drop "%s"' % (username, password, database_name)
            )

        def create_database():
            run_command(
                'mysqladmin --user="%s" --password="%s" create "%s"' % (username, password, database_name)
            )

        drop_database()
        create_database()
        self.execute_file(database_name, username, password, file_path, run_command=run_command)

    def execute_file(self, database_name, username, password, file_path, options='', run_command=run):
        return run_command(
            'mysql --batch --user=%(user)s --password=%(password)s --database=name %(database)s %(options)s < %(file)s' % dict(
                user=username,
                password=password,
                database=database_name,
                options=options,
                file=file_path
            )
        )

    def root_execute(self, sql, options=''):
        return sudo(
            'mysql --batch --user=root --password=%s %s -e "%s"' % (
                self.get_root_password(),
                options,
                sql
            )
        )

    def get_root_password(self):
        if not hasattr(self, '_root_password'):
            self._root_password = prompt(yellow('Password for mysql root user:'))

        return self._root_password

    def restore_local_database(self, backup_file, django_settings):
        database_name = django_settings.DATABASES['default']['NAME']
        database_user = django_settings.DATABASES['default']['USER']
        database_password = django_settings.DATABASES['default']['PASSWORD']

        self.restore_database(database_name, database_user, database_password, backup_file, run_command=local)
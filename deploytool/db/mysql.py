from fabric.colors import yellow
from fabric.operations import prompt, sudo


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
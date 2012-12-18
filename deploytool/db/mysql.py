from fabric.colors import yellow
from fabric.operations import prompt, sudo


class DatabaseOperations(object):
    needs_password = True

    def __init__(self):
        self.root_password = prompt(yellow('Password for mysql root user:'))

    def database_exists(self, database_name):
        output = self.execute(
            "SHOW DATABASES LIKE \'%s\'" % database_name,
            '--skip-column-names'
        )
        return bool(output.strip().lower() == database_name.lower())

    def create_database(self, database_name, owner, password):
        self.execute(r"CREATE DATABASE IF NOT EXISTS \\`%s\\` CHARACTER SET utf8 COLLATE utf8_general_ci" % database_name)

        self.execute(
            r"GRANT ALL PRIVILEGES ON \\`%s\\`.* TO '%s'@'localhost' IDENTIFIED BY '%s' WITH GRANT OPTION" % (
                database_name,
                owner,
                password
            )
        )
        self.execute('FLUSH PRIVILEGES')

    def execute(self, sql, options=''):
        return sudo(
            'mysql --batch --user=root --password=%s %s -e "%s"' % (
                self.root_password,
                options,
                sql
            )
        )
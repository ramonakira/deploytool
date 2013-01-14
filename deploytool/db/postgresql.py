from fabric.operations import sudo, run


class DatabaseOperations(object):
    needs_password = False
    engine_name = 'postgresql_psycopg2'

    def database_exists(self, database_name):
        output = self.execute("select 1 from pg_database where datname='%s'" % database_name)
        return output == '1'

    def create_database(self, database_name, owner, password):
        if not self.user_exists(owner):
            self.sudo_postgres('createuser %s' % owner)

        if not self.database_exists(database_name):
            self.sudo_postgres('createdb %s -O %s' % (database_name, owner))

    def backup_database(self, database_name, username, password, file_path):
        run(
            'pg_dump --no-owner %s > %s' % (database_name, file_path)
        )

    def restore_database(self, database_name, username, password, file_path):
        run('dropdb %s' % database_name)
        self.create_database(database_name, username, password)
        run('psql -d %s -f %s' % (database_name, file_path))

    def execute(self, sql):
        return sudo(
            'psql -t -A -c "%s"' % sql,
            user='postgres'
        )

    def sudo_postgres(self, command):
        return sudo(command, user='postgres')

    def user_exists(self, user):
        output = self.execute("SELECT 1 FROM pg_roles WHERE rolname='%s'" % user)
        return output == '1'
from fabric.operations import sudo


class DatabaseOperations(object):
    needs_password = False
    engine_name = 'postgresql_psycopg2'

    def database_exists(self, database_name):
        output = self.execute("select 1 from pg_database where datname='%s'" % database_name)
        return output == '1'

    def create_database(self, database_name, owner, password):
        if not self.database_exists(database_name):
            self.sudo_postgres('createuser %s' % owner)
            self.sudo_postgres('createdb %s -O %s' % (database_name, owner))

    def execute(self, sql):
        return sudo(
            'psql -t -A -c "%s"' % sql,
            user='postgres'
        )

    def sudo_postgres(self, command):
        return sudo(command, user='postgres')
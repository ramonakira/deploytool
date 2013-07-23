from fabric.operations import run


class DatabaseOperations(object):
    needs_password = False
    engine_name = 'postgresql_psycopg2'

    def _create_database(self, database_name, owner):
        command = 'createdb %s --owner=%s --encoding=utf8' % (database_name, owner)

        run(command)

    def backup_database(self, database_name, username, password, file_path):
        run(
            'pg_dump --no-owner %s > %s' % (database_name, file_path)
        )

    def restore_database(self, database_name, username, password, file_path):
        run('dropdb %s' % database_name)
        self._create_database(database_name, username)
        run('psql -d %s -f %s' % (database_name, file_path))
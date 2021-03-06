from fabric.operations import sudo, run, local


class DatabaseOperations(object):
    needs_password = False
    engine_name = 'postgresql_psycopg2'

    def database_exists(self, database_name):
        output = self.execute("select 1 from pg_database where datname='%s'" % database_name)
        return output == '1'

    def create_database(self, database_name, owner, password):
        if not self.user_exists(owner):
            self.sudo_postgres('createuser %s --createdb --no-superuser --no-createrole' % owner)

        if not self.database_exists(database_name):
            self._create_database(database_name, owner, True)

    def _create_database(self, database_name, owner, sudo):
        command = 'createdb %s --owner=%s --encoding=utf8' % (database_name, owner)

        if sudo:
            self.sudo_postgres(command)
        else:
            run(command)

    def backup_database(self, database_name, username, password, file_path):
        run(
            'pg_dump --no-owner %s > %s' % (database_name, file_path)
        )

    def restore_database(self, database_name, username, password, file_path):
        run('dropdb %s' % database_name)
        self._create_database(database_name, username, False)
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

    def restore_local_database(self, backup_file, django_settings):
        database_name = django_settings.DATABASES['default']['NAME']
        database_user = django_settings.DATABASES['default']['USER']

        result = local('dropdb --if-exists %s' % database_name)

        if result.return_code != 0:
            raise Exception('Could not remove local database')
        else:
            local('createdb %s --owner=%s --encoding=utf8' % (database_name, database_user))
            local('psql -d %s -f %s' % (database_name, backup_file))
            local('rm %s' % backup_file)

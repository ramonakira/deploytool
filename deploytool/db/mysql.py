from fabric.operations import run


class DatabaseOperations(object):
    needs_password = True
    engine_name = 'mysql'

    def backup_database(self, database_name, username, password, file_path):
        command = 'mysqldump --user=\'%s\' --password=\'%s\' \'%s\' > %s' % (
            username,
            password.replace("'", "\\'"),
            database_name,
            file_path
        )
        run(command)

    def restore_database(self, database_name, username, password, file_path):
        def drop_database():
            run(
                'mysqladmin -f --user="%s" --password="%s" drop "%s"' % (username, password, database_name)
            )

        def create_database():
            run(
                'mysqladmin --user="%s" --password="%s" create "%s"' % (username, password, database_name)
            )

        drop_database()
        create_database()
        self.execute_file(username, password, file_path)

    def execute_file(self, username, password, file_path, options=''):
        return run(
            'mysql --batch --user=%s --password=%s %s < %s' % (
                username,
                password,
                options,
                file_path
            )
        )
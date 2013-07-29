from fabric.operations import run


def backup_database(database_name, username, file_path):
    run(
        'pg_dump --no-owner %s > %s' % (database_name, file_path)
    )


def restore_database(database_name, username, file_path):
    run('dropdb %s' % database_name)

    _create_database(database_name, username)

    run('psql -d %s -f %s' % (database_name, file_path))


def _create_database(database_name, owner):
    command = 'createdb %s --owner=%s --encoding=utf8' % (database_name, owner)

    run(command)
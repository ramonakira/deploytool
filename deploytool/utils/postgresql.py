from fabric.operations import run


def backup_database(database_name, username, file_path):
    run(
        'pg_dump --no-owner %s > %s' % (database_name, file_path)
    )


def restore_database(database_name, username, file_path):
    result = run('dropdb %s' % database_name)

    if result.failed:
        raise Exception('Could not drop the database')

    _create_database(database_name, username)

    result = run('psql -d %s -f %s' % (database_name, file_path))

    if result.failed:
        raise Exception('Could not restore the database')


def _create_database(database_name, owner):
    command = 'createdb %s --owner=%s --encoding=utf8' % (database_name, owner)

    result = run(command)

    if result.failed:
        raise Exception('Could not create the database')

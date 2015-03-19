from fabric.operations import run


def backup_database(database_name, username, file_path):
    command = ['pg_dump --no-owner %(db)s']
    if file_path.endswith('.gz'):
        command.append('| gzip')
    command.append('> %(path)s')
    command = ' '.join(command)
    run(command % {'db': database_name, 'path': file_path})


def restore_database(database_name, username, file_path):
    result = run('dropdb %s' % database_name)

    if result.failed:
        raise Exception('Could not drop the database')

    _create_database(database_name, username)

    if file_path.endswith('.gz'):
        command = 'gunzip -c %(path)s | psql -d %(db)s'
    else:
        command = 'psql -d %(db)s -f %(path)s'
    result = run(command % {'db': database_name, 'path': file_path})

    if result.failed:
        raise Exception('Could not restore the database')


def _create_database(database_name, owner):
    command = 'createdb %s --owner=%s --encoding=utf8' % (database_name, owner)

    result = run(command)

    if result.failed:
        raise Exception('Could not create the database')

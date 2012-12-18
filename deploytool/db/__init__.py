def get_database_operations(engine_name):
    module = __import__('deploytool.db.%s' % engine_name, fromlist=['DatabaseOperations'])

    return module.DatabaseOperations()
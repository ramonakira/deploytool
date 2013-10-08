from fabric.colors import yellow, green
from fabric.tasks import Task
from fabric.api import settings, hide, local, open_shell


class ListTasks(Task):
    """ GENE - Parses `fab --list` and displays custom categorized list """

    name = 'list'
    categories = {
        'PROV': 'Provisioning',
        'REMO': 'Deployment',
        'HOST': 'Environments',
    }

    def run(self):

        # hide all fabric output
        with settings(hide('warnings', 'running', 'stdout', 'stderr'), warn_only=True):

            # grab output from fabric's task list
            output = local('fab --list', capture=True)
            # filter for indented tasks and split to list
            lines = [t for t in output.split('\n') if t != '' and t[0].isspace()]
            task_list = []
            max_name_length = 0

            # create custom task list from fabric list output
            for line in lines:
                words = str.split(line)
                _name = words[0]

                if len(words) > 1:
                    _category = words[1]
                    _description = str.join(' ', words[3:])

                    if _category in self.categories.keys():
                        task_list.append({
                            'name': _name,
                            'category': _category,
                            'description': _description,
                        })

                        max_name_length = max(max_name_length, len(_name))

            # display pretty custom categorized list
            print(yellow('\n+-----------------+\n| Available tasks |\n+-----------------+'))
            task_list.sort()
            current_category = ''

            for task in task_list:
                if task['category'] != current_category:
                    current_category = task['category']
                    print(green('  \n  %s' % self.categories[current_category]))
                task['spaces'] = ' ' * (max_name_length - len(task['name']))
                print('    %(name)s%(spaces)s\t%(description)s' % task)


class ShellTask(Task):
    name = 'shell'

    def run(self):
        open_shell()
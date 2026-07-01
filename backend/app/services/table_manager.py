current_table = None


def set_current_table(table_name):
    global current_table
    current_table = table_name


def get_current_table():
    return current_table
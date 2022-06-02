class basic_setting(object):
    JSONIFY_PRETTYPRINT_REGULAR=True
    JSON_SORT_KEYS=False
    TASK_ROOT="./app"
    TASK_CFG_NAME="task.json"
    TASK=dict()
    TASK_LIST=dict()
    UUID=dict()
    RE_UUID=dict()
    SRC=dict()
    ALLOWED_HOSTS = ['*']
    RE_SRC='0',
    AF='tensorrt'

class config(object):
    JSONIFY_PRETTYPRINT_REGULAR = True
    JSON_SORT_KEYS              = False
    TASK_ROOT       = "./task"
    TASK_CFG_NAME   = "task.json"
    TASK            = dict()
    TASK_LIST       = dict()
    APPLICATION     = dict()
    UUID            = dict()
    RE_UUID         = dict()
    SRC             = dict()
    ALLOWED_HOSTS   = ['*']
    RE_SRC          = '0'
    SOCK_POOL            = dict()

    MQTT_BROKER_URL = ""
    MQTT_USERNAME   = ""
    MQTT_PASSWORD   = ""
    MQTT_BROKER_PORT   = 1883
    
    TB_API_REG_DEVICE   = "/api/v1/devices"
    TB_TOPIC_REC_RPC    = "v1/devices/me/rpc/request/"
    TB_TOPIC_SND_RPC    = "v1/devices/me/rpc/response/"
    
    TB_DEVICE_ID        = ''
    TB_TOKEN            = ''
    TB_CREATE_TIME      = ''

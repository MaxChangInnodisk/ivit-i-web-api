class config(object):
    
    JSONIFY_PRETTYPRINT_REGULAR = True
    JSON_SORT_KEYS              = False
    TASK_ROOT       = "./task"
    TASK_CFG_NAME   = "task.json"
    DEBUG           = False

    PLATFORM        = "intel"
    FRAMEWORK       = "openvino"

    TASK            = dict()
    TASK_LIST       = dict()
    APPLICATION     = dict()
    UUID            = dict()
    
    MODEL           = dict()
    MODEL_TASK      = dict()
    MODEL_APP       = dict()

    SRC             = dict()
    ALLOWED_HOSTS   = ['*']
    SOCK_POOL       = dict()
    IVIT_WS_POOL    = dict()
    INFER_WS_POOL   = dict()

    MQTT_BROKER_URL = ""
    MQTT_USERNAME   = ""
    MQTT_PASSWORD   = ""
    MQTT_BROKER_PORT    = 1883
    MQTT_KEEPALIVE      = 5
    MQTT_REFRESH_TIME   = 1.0

    TB_API_REG_DEVICE   = "/api/v1/devices"
    TB_TOPIC_REC_RPC    = "v1/devices/me/rpc/request/"          # +
    TB_TOPIC_SND_RPC    = "v1/devices/me/rpc/response/"         # {n}

    TB_TOPIC_REC_ATTR   = "v1/devices/me/attributes"
    TB_TOPIC_SND_ATTR   = "v1/devices/me/attributes/response/"  # +

    TB_TOPIC_SND_TEL    = "v1/devices/me/telemetry"


    TB_DEVICE_ID        = ''
    TB_TOKEN            = ''
    TB_CREATE_TIME      = ''

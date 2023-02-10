import logging, subprocess, json, os
from flask import Blueprint, abort, jsonify, request
from flasgger import swag_from
from ivit_i.utils.err_handler import handle_exception
from ..tools.thingsboard import send_get_api, send_post_api
from .common import sock, app, mqtt
from ..tools.common import get_address
from .task import get_simple_task

YAML_PATH   = "../docs/icap"
BP_NAME     = "icap"
bp_icap = Blueprint(BP_NAME, __name__)

DEVICE_TYPE         = "IVIT-I"
DEVICE_NAME         = "ivit-{}".format(get_address())
DEVICE_ALIAS        = DEVICE_NAME

# API Method
GET     = 'GET'
POST    = 'POST'

# Basic
TASK        = "TASK"
TASK_LIST   = "TASK_LIST"
HOST        = "HOST"
PORT        = "PORT"

# Define App Config Key
TB                  = "TB"
TB_PORT             = "TB_PORT"
TB_API_REG_DEVICE   = "TB_API_REG_DEVICE"

KEY_TB_CREATE_TIME  = "TB_CREATE_TIME"
KEY_TB_DEVICE_ID    = "TB_DEVICE_ID"
KEY_TB_TOKEN        = "TB_TOKEN"

KEY_TB_STATS        = "TB_STATS"
KEY_DEVICE_TYPE     = "TB_DEV_TYPE"
KEY_DEVICE_NAME     = "TB_DEV_NAME"
KEY_DEVICE_ALIAS    = "TB_DEV_ALAIS"

MQTT_BROKER_URL = "MQTT_BROKER_URL"
MQTT_USERNAME   = "MQTT_USERNAME"

TB_TOPIC_REC_RPC = "TB_TOPIC_REC_RPC"

# Define Thingsboard return key
TB_KEY_NAME     = "name" 
TB_KEY_TYPE     = "type" 
TB_KEY_ALIAS    = "alias"

TB_KEY_TIME         = "createdTime"
TB_KEY_TOKEN_TYPE   = "credentialsType"
TB_KEY_ID           = "id"
TB_KEY_TOKEN        = "accessToken"

def register_tb_device(tb_url):
    """
    Register Thingsboard Device
    ---
    - Web API: http://10.204.16.110:3000/api/v1/devices
    - Method: POST
    - Data:
        - Type: JSON
        - Content: {
                "name"  : "ivit-i-{IP}",
                "type"  : "IVIT-I",
                "alias" : "ivit-i-{IP}"
            }
    - Response:
        - Type: JSON
        - Content: {
                "data": {
                    "createdTime": 1662976363031,
                    "credentialsType": "ACCESS_TOKEN",
                    "id": "a5636270-3280-11ed-a9c6-9146c0c923c4",
                    "accessToken": "auWZ5o6exyX9eWEmm7p3"
                }
            }
    """
    
    create_time, device_id, device_token = "", "", ""

    send_data = { 
        TB_KEY_NAME  : DEVICE_NAME,
        TB_KEY_TYPE  : DEVICE_TYPE,
        TB_KEY_ALIAS : DEVICE_ALIAS
    }

    header = "http://"
    if ( not header in tb_url ): tb_url = header + tb_url

    timeout = 3
    # logging.warning("[ iCAP ] Register Thingsboard Device ... ( Time Out: {}s ) \n{}".format(timeout, send_data))
    
    ret, data = send_post_api(tb_url, send_data, timeout=timeout, stderr=False)
    print(ret, data)
    # Register sucess
    if(ret):
        logging.info("[ iCAP ] Register Thingsboard Device ... Pass !")
        logging.info("Send Request: {}".format(data))        
        logging.info("Get Response: {}".format(data))

        data            = data["data"]
        create_time     = data[TB_KEY_TIME]
        device_id       = data[TB_KEY_ID]
        device_token    = data[TB_KEY_TOKEN]
    else:
        logging.warning("[ iCAP ] Register Thingsboard Device ... Failed !")
        logging.warning("   - API: {}".format( tb_url ))
        logging.warning("   - TOKEN: {}".format( TB_KEY_TOKEN ))
        
    return ret, (create_time, device_id, device_token)

def send_basic_attr():
    """
    Send basic information ( attribute ) to iCAP (Thingsboard)
    
    IP, PORT, AI Tasks
    """
    K_IP    = "web_forward_url"
    TASK_KEY    = "task"

    send_topic  = "v1/devices/me/attributes"

    with app.app_context():
        ret_data = get_simple_task()

    json_data   = {
        K_IP: f'{app.config[HOST]}:{app.config["DEMO_SITE_PORT"]}',
        TASK_KEY: ret_data
    }
    logging.info('Send Shared Attributes at first time...\n * Topic: {}\n * Content: {}'.format(
        send_topic, json_data
    ))

    mqtt.publish(send_topic, json.dumps(json_data))

def init_for_icap():
    """ Register iCAP
    ---
    1. Update `MQTT_BROKER_URL` from `ivit-i.json`
    2. Update `KEY_TB_STATS`, `KEY_DEVICE_TYPE`, `KEY_DEVICE_NAME`, `KEY_DEVICE_ALIAS` to 

    """
    
    # Pass the init icap if not setup
    if app.config.get(TB)=='' or app.config[TB_PORT]== '':
        return None 

    # Update MQTT URL
    app.config[MQTT_BROKER_URL] = app.config[TB]

    # Store value in app.config
    ivit_device_info = {    KEY_TB_STATS: False,
                            KEY_DEVICE_TYPE: DEVICE_TYPE,
                            KEY_DEVICE_NAME: DEVICE_NAME,
                            KEY_DEVICE_ALIAS: DEVICE_ALIAS  }
    ( logging.info('Update {}: {}'.format(key, val)) for key, val in ivit_device_info.items() ) 
    app.config.update(ivit_device_info)
    
    # Combine URL
    register_url = "{}:{}{}".format(
        app.config[TB], 
        app.config[TB_PORT],
        app.config[TB_API_REG_DEVICE]
    )

    # Register thingboard device
    ret, (create_time, device_id, device_token) = register_tb_device(register_url)

    # Update Information
    if(ret):
        app.config[KEY_TB_STATS] = True
        for key, val in zip( [KEY_TB_CREATE_TIME, KEY_TB_DEVICE_ID, KEY_TB_TOKEN, MQTT_USERNAME], [create_time, device_id, device_token, device_token] ):
            logging.info('Update {}: {}'.format(key, val))
            app.config.update( {key:val} )
        
        mqtt.init_app(app)
        logging.info('Initialized MQTT for iVIT-I !')

    return ret

def register_mqtt_event():

    @mqtt.on_connect()
    def handle_mqtt_connect(client, userdata, flags, rc):
        logging.info("Connecting to Thingsboard")
        if rc == 0:
            logging.info('Connected successfully')
            _topic = app.config[TB_TOPIC_REC_RPC]+'+'
            mqtt.subscribe(_topic)
            logging.info('Subcribe: {}'.format(_topic))
        else:
            logging.error('Bad connection. Code:', rc)
        
        send_basic_attr()
        logging.info('Send Basic Information')

    @mqtt.on_message()
    def handle_mqtt_message(client, userdata, message):
        """
        Handle the MQTT Message
        ---
        Data Format:
            - type: json
            - params:
                - method: 
                    - type: string
                    - example: support GET, POST, 'PUT', 'DEL',
                - params: 
                    - api   :
                        - type: string
                        - example: /task
                    - data  : 
                        - type: json
                        - descr: the payload of the web api which only support json format
                        - example: { 'uuid': xasdadsa }
        """
        topic = message.topic
        payload = message.payload.decode()
        data = json.loads(payload)

        logging.warning("Receive Data from Thingsboard \n  - Topic : {} \n  - Data: {}".format(topic, data))
        request_idx = topic.split('/')[-1]
        
        method  = data["method"].upper()
        params  = data["params"]
        web_api = params["api"]
        data    = params["data"] if "data" in params else None

        trg_url = "http://{}:{}{}".format(app.config['HOST'], app.config['PORT'], web_api)

        # send_data = json.dumps({ "data": "test" })
        ret, resp = send_get_api(trg_url) if method.upper() == "GET" else send_post_api(trg_url, send_data)
        
        send_data = json.dumps(resp)
        send_topic  = app.config['TB_TOPIC_SND_RPC']+f"{request_idx}"

        logging.warning("Send Data from iVIT-I \n  - Topic : {} \n  - Data: {}".format(
            send_topic, 
            send_data
        ))
        
        mqtt.publish(send_topic, send_data)

def get_tb_info():
    return {
        KEY_TB_STATS: app.config[KEY_TB_STATS],
        KEY_DEVICE_NAME: app.config[KEY_DEVICE_NAME],
        KEY_DEVICE_TYPE: app.config[KEY_DEVICE_TYPE],
        KEY_DEVICE_ALIAS: app.config[KEY_DEVICE_ALIAS],
        KEY_TB_CREATE_TIME: app.config[KEY_TB_CREATE_TIME],
        KEY_TB_DEVICE_ID: app.config[KEY_TB_DEVICE_ID],
        KEY_TB_TOKEN: app.config[KEY_TB_TOKEN],
    }

@bp_icap.route("/get_my_ip", methods=[GET])
def get_my_ip():
    return jsonify( {'ip': request.remote_addr} ), 200

@bp_icap.route("/icap/info", methods=[GET])
def icap_info():
    return jsonify(get_tb_info()), 200

@bp_icap.route("/icap/device/id", methods=[GET])
def get_device_id():
    return jsonify( { "device_id": app.config.get(KEY_TB_DEVICE_ID) } ), 200

@bp_icap.route("/icap/device/type", methods=[GET])
def get_device_type():
    return jsonify( { "device_type": app.config.get(KEY_DEVICE_TYPE) } ), 200

@bp_icap.route("/icap/addr", methods=[GET])
def get_addr():
    return jsonify( { "ip" : str(app.config[TB]), "port": str(app.config[TB_PORT]) } ), 200

@bp_icap.route("/icap/addr", methods=[POST])
@bp_icap.route("/icap/register", methods=[POST])
def modify_addr():

    K_IP = "ip"
    K_PORT = "port"

    # Get data: support form data and json
    data = dict(request.form) if bool(request.form) else request.get_json()

    # Check data
    if data is None:
        msg = 'Get empty data, please make sure the content include "ip" and "port". '
        logging.error(msg)        
        return jsonify(msg), 400

    # Check ip
    ip = data.get(K_IP)
    if ip is None:
        msg = "Get empty ip address ... "
        logging.error(msg); 
        return jsonify(msg), 400
    
    # Check port
    port = data.get(K_PORT)
    if port is None:
        msg = "Get empty port number ... "
        logging.error(msg); 
        return jsonify(msg), 400
    
    app.config.update({
        TB: ip,
        TB_PORT: port 
    })
        
    try:
        if(init_for_icap()):
            register_mqtt_event()
            return jsonify( get_tb_info() ), 200
        else:
            return jsonify( 'Connect to iCAP ... Failed' ), 400

    except Exception as e:
        return jsonify( handle_exception(e) ), 400

import logging, subprocess, json, os
from flask import Blueprint, abort, jsonify, request
from flasgger import swag_from
from ivit_i.utils.err_handler import handle_exception
from ..tools.thingsboard import get_api, post_api
from .common import sock, app, mqtt
from ..tools.common import get_address
from .task import get_simple_task

YAML_PATH   = "/workspace/ivit_i/web/docs/icap"
BP_NAME     = "icap"
bp_icap = Blueprint(BP_NAME, __name__)

TASK        = "TASK"
TASK_LIST   = "TASK_LIST"
HOST        = "HOST"
PORT        = "PORT"

TB                  = "TB"
TB_PORT             = "TB_PORT"
TB_API_REG_DEVICE   = "TB_API_REG_DEVICE"

TB_CREATE_TIME  = "TB_CREATE_TIME"
TB_DEVICE_ID    = "TB_DEVICE_ID"
TB_TOKEN        = "TB_TOKEN"

MQTT_BROKER_URL = "MQTT_BROKER_URL"
MQTT_USERNAME   = "MQTT_USERNAME"

TB_TOPIC_REC_RPC = "TB_TOPIC_REC_RPC"

TB_KEY_NAME     = "name" 
TB_KEY_TYPE     = "type" 
TB_KEY_ALIAS    = "alias"

TB_KEY_TIME_CREATE  = "createdTime"
TB_KEY_TOKEN_TYPE   = "credentialsType"
TB_KEY_ID           = "id"
TB_KEY_TOKEN        = "accessToken"

TB_TYPE         = "IVIT-I"
TB_NAME         = "ivit-{}".format(get_address())
TB_ALIAS        = TB_NAME

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
        TB_KEY_NAME  : TB_NAME,
        TB_KEY_TYPE  : TB_TYPE,
        TB_KEY_ALIAS : TB_ALIAS
    }

    header = "http://"
    if ( not header in tb_url ): tb_url = header + tb_url

    timeout = 3
    # logging.warning("[ iCAP ] Register Thingsboard Device ... ( Time Out: {}s ) \n{}".format(timeout, send_data))
    
    ret, data    = post_api(tb_url, send_data, timeout=timeout, stderr=False)
    data = data["data"]
    
    if(ret==200):
        logging.info("[ iCAP ] Register Thingsboard Device ... Pass !")
        logging.info("Send Request: {}".format(data))        
        logging.info("Get Response: {}".format(data))

        data            = data["data"]
        create_time     = data[TB_KEY_TIME_CREATE]
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
    ADDR_KEY    = "web_forward_url"
    TASK_KEY    = "task"

    send_topic  = "v1/devices/me/attributes"

    with app.app_context():
        ret_data = get_simple_task()

    json_data   = {
        ADDR_KEY: f'{app.config[HOST]}:{app.config["DEMO_SITE_PORT"]}',
        TASK_KEY: ret_data
    }
    logging.info('Send Shared Attributes at first time...\n * Topic: {}\n * Content: {}'.format(
        send_topic, json_data
    ))

    mqtt.publish(send_topic, json.dumps(json_data))

def init_for_icap():
    """
    Check if need iCAP

        1. Check configuration
        2. Concatenate URL for thingsboard
        3. Registering thingsboard device
    """
    
    # Pass the init icap if not setup
    if app.config.get(TB)=='' or app.config[TB_PORT]== '':
        return None 

    # Define MQTT URL
    app.config[MQTT_BROKER_URL] = app.config[TB]
    
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
        app.config[TB_CREATE_TIME] = create_time
        app.config[TB_DEVICE_ID] = device_id
        app.config[TB_TOKEN] = app.config[MQTT_USERNAME] = device_token
        mqtt.init_app(app)
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
                    - example: support 'GET', 'POST', 'PUT', 'DEL',
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
        ret, resp = get_api(trg_url) if method.upper() == "GET" else post_api(trg_url, data)
        
        send_data = json.dumps(resp)
        send_topic  = app.config['TB_TOPIC_SND_RPC']+f"{request_idx}"

        logging.warning("Send Data from iVIT-I \n  - Topic : {} \n  - Data: {}".format(
            send_topic, 
            send_data
        ))
        
        mqtt.publish(send_topic, send_data)

@bp_icap.route("/get_my_ip/", methods=['GET'])
def get_my_ip():
    return jsonify({'ip': request.remote_addr}), 200

@bp_icap.route("/icap/register/", methods=['POST'])
def icap_register():

    ADDR_KEY = "address"

    # Get data: support form data and json
    data = dict(request.form) if bool(request.form) else request.get_json()

    if data is None:
        logging.info('Using default address: "{}:{}"'.format(
            app.config.get(TB), app.config.get(TB_PORT)
        ))
    else:
        new_addr = data.get(ADDR_KEY)
        if new_addr is None:
            msg = "Unexcepted data, make sure the key is {} ... ".format(ADDR_KEY)
            logging.error(msg); 
            return jsonify(msg), 400
        
        ip,port = new_addr.split(':')
        app.config.update({
            TB: ip,
            TB_PORT: port 
        })
        
    try:
        if(init_for_icap()):
            register_mqtt_event()
            
            return jsonify( app.config.get('TB_DEVICE_ID') ), 200
        else:
            return jsonify( 'Connect to iCAP ... Failed' ), 400

    except Exception as e:
        return jsonify( handle_exception(e) ), 400

@bp_icap.route("/icap/get_device_id/", methods=['GET'])
def get_tb_id():
    return jsonify( app.config.get('TB_DEVICE_ID') ), 200

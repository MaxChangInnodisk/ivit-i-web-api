import logging, subprocess, json, os, threading, wget, time, shutil, hashlib
import subprocess as sb
import numpy as np
from flask import Blueprint, abort, request
from flasgger import swag_from

from ivit_i.utils.err_handler import handle_exception

from ..tools.thingsboard import send_get_api, send_post_api

from .common import sock, app, mqtt
from ..tools.common import get_address, get_mac_address, http_msg, simple_exception
from .task import get_simple_task
from .operator import parse_info_from_zip
from ..tools.handler import init_model

YAML_PATH   = "../docs/icap"
BP_NAME     = "icap"
bp_icap = Blueprint(BP_NAME, __name__)

DEVICE_TYPE         = "iVIT-I"
DEVICE_NAME         = "{}-{}".format(DEVICE_TYPE, get_mac_address())
DEVICE_ALIAS        = DEVICE_NAME

# API Method
GET     = 'GET'
POST    = 'POST'

# Basic
TASK        = "TASK"
TASK_LIST   = "TASK_LIST"
HOST        = "HOST"
PORT        = "PORT"
PLATFORM    = "PLATFORM"

INTEL = "intel"
NVIDIA = "nvidia"
JETSON = "jetson"
XILINX = "xilinx"

MODEL_KEY       = 'MODEL'
MODEL_TASK_KEY  = "MODEL_TASK"
MODEL_APP_KEY   = 'MODEL_APP'
TAG_APP         = 'TAG_APP'

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

TB_TOPIC_REC_RPC    = "TB_TOPIC_REC_RPC"
TB_TOPIC_REC_ATTR   = "TB_TOPIC_REC_ATTR"
TB_TOPIC_SND_ATTR   = "TB_TOPIC_SND_ATTR"
TB_TOPIC_SND_TEL    = "TB_TOPIC_SND_TEL"

# Define Thingsboard return key
TB_KEY_NAME     = "name" 
TB_KEY_TYPE     = "type" 
TB_KEY_ALIAS    = "alias"
TB_KEY_MODEL    = "production_model"

TB_KEY_TIME         = "createdTime"
TB_KEY_TOKEN_TYPE   = "credentialsType"
TB_KEY_ID           = "id"
TB_KEY_TOKEN        = "accessToken"

# Define TELEMETRY STATE
S_ERRO = "ERROR"
S_FAIL = "FAILED"
S_PASS = "PASS"
S_INIT = "INITIALIZED"
S_DOWN = "DOWNLOADING"
S_DOWN_END = "DOWNLOADED"
S_PARS = "PARSED"
S_CONV = "CONVERTED"
S_FINISH = "FINISHED"

class ICAP_DEPLOY:

    def __init__(self, data) -> None:
        """ iCAP Deployment Event
        
        * Support format 

            {   'sw_title': '892616d0-ada4-11ed-b82d-df49313d086e-fire_detection-intel', 
                'sw_version': '1.1', 
                'sw_tag': '892616d0-ada4-11ed-b82d-df49313d086e-fire_detection-intel-1.1', 
                'sw_url': 'http://10.204.16.110:9527/file/ota_repo/892616d0-ada4-11ed-b82d-df49313d086e-fire_detection-intel.zip'
                'sw_description': '{
                    "description": {
                        "project_name": "fire_detection",
                        "file_id": "892616d0-ada4-11ed-b82d-df49313d086e-fire_detection-intel.zip",
                        "file_size": 117645240,
                        "checksum": "ed53ae670f3105543a7489fab4fdf0b6",
                        "checksumAlgorithm": "MD5",
                        "model_type": "obj",
                        "model_classes": [
                            "fire"
                        ]
                    },
                    "applyProductionModel": "intel"
                }'
            }
        """

        # Need Convert List
        self.convert_platform = [ NVIDIA, JETSON ]
        self.parsed_info = None
        self.converted_info = None
        
        self.temp_root = app.config["TEMP_PATH"]
        self.model_root = app.config["MODEL_DIR"]

        # Get Basic Data
        self.title          = data["sw_title"]
        self.ver            = data["sw_version"]
        self.tag            = data["sw_tag"]
        self.url            = data["sw_url"]
        self.checksum       = data["sw_checksum"]
        self.checksum_type  = data["sw_checksum_algorithm"]
        self.descr          = data["sw_description"]        
        
        # Get Description Data
        self.platform = self.descr.get("applyProductionModel")
        self.project_name   = self.descr["project_name"]
        self.file_name      = self.descr["file_id"]
        self.file_size      = self.descr["file_size"]
        self.model_type     = self.descr["model_type"]
        self.model_classes  = self.descr["model_classes"]

        # Check platform
        self.check_platform()

        # Combine Save and Target Path
        self.save_path = os.path.join(self.temp_root, self.file_name )
        self.target_path = os.path.join(self.model_root, self.project_name )
        
        # Removing Exist Path
        self.clear_exist_data()

        # Update Download Parameters
        self.tmp_proc_rate = 0  # avoid keeping send the same proc_rate
        self.push_rate = 10

        # Create Thread
        self.t = threading.Thread(target=self.deploy_event, daemon=True)

    def check_platform(self):
        if not self.platform:
            return

        pla_error = False
        ivit_pla = app.config["PLATFORM"].lower()
        model_pla = self.platform.lower()
        
        # Check Platform Value is Correct
        if ( ivit_pla != model_pla ):
            pla_error = True

        # NVIDIA and Jetson Platform is shared
        if ivit_pla in [ JETSON, NVIDIA ]:
            pla_matrix = np.array([ ivit_pla, model_pla ] ).reshape(1, -1)
            pla_matrix_rev = np.array( [ NVIDIA, JETSON ] ).reshape(-1, 1)
            if ( True in (pla_matrix == pla_matrix_rev) ):
                pla_error = False

        # Platform Error        
        if pla_error:
            mesg = 'Unexepted Platform: {}'.format(self.platform)
            self.error(mesg)
            raise TypeError(mesg)

    def check_md5(self):
        """ Checking checksum by MD5 """
        checksum = hashlib.md5(open(self.save_path,'rb').read()).hexdigest()
        if checksum != self.checksum:
            raise TypeError("Checksum Error !!!!")
        logging.warning("Checked By Checksum ( MD5 )")
        
    def clear_exist_data(self):
        """ Clear exist data ( self.save_path, self.target_path ) """
        for path in [ self.save_path, self.target_path]:
            if os.path.exists(path):
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            logging.warning('Clear exist path: {}'.format(path))

    def bar_progress(self, current, total, width=80):
        """ Custom progress bar for iCAP deployment, which will push the progress to icap """
        proc_rate = int(current / total * 100)
        proc_mesg = f"{S_DOWN} ( {proc_rate}% )"

        if ((proc_rate%self.push_rate)==0 and proc_rate!=self.tmp_proc_rate) :
            self.tmp_proc_rate = proc_rate
            # logging.debug(proc_mesg)
            self.push_to_icap(state=proc_mesg)

    def print_info(self):
        print()
        print("="*40, '\n')
        print('# Deploy Information')
        print('\t * {}: {}'.format( 'SW_TITLE', self.title))
        print('\t * {}: {}'.format( 'SW_VERSION', self.ver))
        print('\t * {}: {}'.format( 'SW_TAG', self.tag))
        print('\t * {}: {}'.format( 'SW_URL', self.url))
        print('\t * {}: {}'.format( 'SW_DESCRIPTION', "Default" if self.descr == None else "Custom"))
        print('# Model Information')
        print('\t * {}: {}'.format('MODEL_NAME', self.file_name))
        print('\t * {}: {}'.format('MODEL_SIZE', self.file_size))
        print('\t * {}: {}'.format('MODEL_CHECKSUM', self.checksum))
        print("="*40, '\n')

    def deploy_event(self):
        """ Deployment Event for iCAP
        1. Downloaded
        2. Parsed
        3. Converted
        4. Finished
        """
        try:
            self.download_event()
            self.parse_event()
            self.convert_event()
            self.finished_event()

        except Exception as e:
            handle_exception(e)
            self.clear_exist_data()
            self.push_to_icap(state=S_ERRO)


    def download_event(self):
        """ Download Event in python thread """
        logging.info('Start to download file ....')
        self.print_info()
        self.push_to_icap(state=S_INIT)

        t_start = time.time()
        wget.download( 
            self.url, 
            self.save_path, 
            bar=self.bar_progress )
        logging.info("Downloaded File from iCAP")

        # Checksum
        self.check_md5()

        logging.info('Download Finished  ... {}s'.format(int(time.time()-t_start)) )
        self.push_to_icap(state=S_DOWN_END)

    def parse_event(self):
        """ Parsing data from ZIP File update self.parsed_info """
        
        # Parse information
        with app.app_context():
            
            self.parsed_info = parse_info_from_zip( zip_path = self.save_path )
            if self.parsed_info is None:
                raise RuntimeError("Parsed data is empty")

            [ print(key, val) for key, val in self.parsed_info.items() ]
            
            # NOTE: The new workflow for iCAP
            # Copy to model path and update to app.config
            sb.run(f"mv -f {self.save_path.replace('.zip', '')} {self.target_path}", shell=True)
            
            logging.info('Moved Folder from {} to {}'.format(
                self.save_path, self.target_path ))

            init_model()

            self.push_to_icap(state=S_PARS)
        
    def convert_event(self):
        """  Convert file base on self.parsed_info """

        if ( self.platform in self.convert_platform ):
            logging.warning('Start Convertion ...')
            # update self.converted_info

            # if ( self.converted_info is None ):
            #     raise RuntimeError('Convert data is empty') 
            
        else:
            logging.warning(f'No need convertion, only {self.convert_platform} have to convert but current is {self.platform}')            
                
        self.push_to_icap(state=S_CONV)

    def finished_event(self):
        """  Update app.config """

        time.sleep(1)
        self.push_to_icap(state=S_FINISH)

    def start(self):
        self.t.start()

    def push_to_icap(self, state=S_INIT, error=""):
        if not ( self.title and self.ver ):
            logging.error('Empty title and version ...')
            return None
        
        mqtt.publish(app.config[TB_TOPIC_SND_TEL], json.dumps({
            "current_sw_title": self.title,
            "current_sw_version": self.ver,
            "sw_state": state,
            "sw_error": error
        }) )

    def error(self, content="Unknown Error ..."):
        print("\nError: ", content)
        self.push_to_icap(state=S_ERRO, error=content)
            

def register_tb_device(tb_url):
    """ Register Thingsboard Device
    
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

    send_data = { 
        TB_KEY_NAME  : DEVICE_NAME,
        TB_KEY_TYPE  : DEVICE_TYPE,
        TB_KEY_ALIAS : DEVICE_ALIAS,
        TB_KEY_MODEL : app.config.get("PLATFORM")
    }

    header = "http://"
    if ( not header in tb_url ): tb_url = header + tb_url

    timeout = 3
    # logging.warning("[ iCAP ] Register Thingsboard Device ... ( Time Out: {}s ) \n{}".format(timeout, send_data))
    logging.info('Register iCAP with: {}'.format(send_data))
    ret, data = send_post_api(tb_url, send_data, timeout=timeout, stderr=False)

    # Register sucess
    if not ret:
        logging.warning("[ iCAP ] Register Thingsboard Device ... Failed !")
        logging.warning("Send Request: {}".format(send_data))    
        logging.warning("   - URL: {}".format(tb_url))
        logging.warning("   - TOKEN: {}".format( TB_KEY_TOKEN ))
        logging.warning("   - Response: {}".format(data))
        raise ConnectionError(data)

    logging.info("[ iCAP ] Register Thingsboard Device ... Pass !")
    logging.info("Send Request: {}".format(send_data))        
    logging.info("Get Response: {}".format(data))

    return data


def send_basic_attr(send_mqtt=True):
    """
    Send basic information ( attribute ) to iCAP (Thingsboard)
    
    IP, PORT, AI Tasks
    """
    K_IP    = "ivitUrl"
    TASK_KEY    = "ivitTask"

    with app.app_context():
        ret_data = get_simple_task()

    json_data   = {
        K_IP: f'{app.config[HOST]}:{app.config["NGINX_PORT"]}',
        TASK_KEY: ret_data
    }
    if send_mqtt:

        send_topic  = "v1/devices/me/attributes"

        mqtt.publish(send_topic, json.dumps(json_data))

    return json_data


def init_for_icap():
    """ Register iCAP
    
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
    data = register_tb_device(register_url)

    # Update Information
    data = data["data"]
    icap_status     = True
    create_time     = data[TB_KEY_TIME]
    device_id       = data[TB_KEY_ID]
    device_token    = data[TB_KEY_TOKEN]
    
    for key, val in zip( [KEY_TB_STATS, KEY_TB_CREATE_TIME, KEY_TB_DEVICE_ID, KEY_TB_TOKEN, MQTT_USERNAME], \
                        [ icap_status, create_time, device_id, device_token, device_token] ):
        logging.info('  - Update {}: {}'.format(key, val))
        app.config.update( {key:val} )
    
    mqtt.init_app(app)
    logging.info('Initialized MQTT for iVIT-I !')


def rpc_event(request_idx, data):


    method  = data["method"].upper()
    params  = data["params"]
    web_api = params["api"]
    data    = params.get("data")

    # trg_url = "http://{}:{}{}".format("127.0.0.1", app.config['PORT'], web_api)
    trg_url = "http://{}:{}{}{}".format(
        "127.0.0.1", app.config['NGINX_PORT'], '/ivit', web_api)

    ret, resp = send_get_api(trg_url) if method.upper() == "GET" else send_post_api(trg_url, data)

    send_topic  = app.config['TB_TOPIC_SND_RPC']+f"{request_idx}"
    mqtt.publish(send_topic, json.dumps(resp))

    log_data, dat_limit = str(resp), 100
    log_data = log_data if len(log_data)<dat_limit else log_data[:dat_limit] + ' ...... '
    print("[iCAP] Topic: {}, Data: {}".format(send_topic, log_data))
    

def attr_event(data):

    if 'sw_description' in data.keys():
        logging.warning('Detected url, start to deploy')

        deploy_event = ICAP_DEPLOY( data = data)
        deploy_event.start()

def register_mqtt_event():

    @mqtt.on_connect()
    def handle_mqtt_connect(client, userdata, flags, rc):
        logging.info("Connecting to Thingsboard")
        
        # Connect Success
        if rc == 0:
            
            logging.info('Connected successfully')

            # For Basic
            for topic in [ TB_TOPIC_REC_ATTR ]:
                mqtt.subscribe(app.config[topic]) # subscribe topic
                logging.info('  - Subscribed: {}'.format(app.config[topic]))

            # For Receive Command From RPC, and Send Attribute
            for topic in [ TB_TOPIC_REC_RPC, TB_TOPIC_SND_ATTR ]:
                _topic = app.config[topic] + "+"
                mqtt.subscribe(_topic)
                logging.info('  - Subcribe: {}'.format(_topic))

        # Connect Failed
        else: logging.error('Bad connection. Code:', rc)
        
        # Send Shared Attribute to iCAP
        send_basic_attr()

    @mqtt.on_message()
    def handle_mqtt_message(client, userdata, message):
        """
        Handle the MQTT Message
        
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

        logging.debug("[iCAP] Receive Data from Thingsboard \n  - Topic : {} \n  - Data: {}".format(topic, data))
        try:
            if app.config[TB_TOPIC_REC_RPC] in topic:
                request_idx = topic.split('/')[-1]
                rpc_event(request_idx, data)

            elif app.config[TB_TOPIC_REC_ATTR] in topic:
                attr_event(data)

        except Exception as e:
            logging.exception(e)


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


@bp_icap.route("/get_basic_attr", methods=[GET])
def get_basic_attr():
    return http_msg( send_basic_attr(send_mqtt=False), 200 )


@bp_icap.route("/get_my_ip", methods=[GET])
def get_my_ip():
    return http_msg( {'ip': request.remote_addr}, 200 )


@bp_icap.route("/icap/info", methods=[GET])
@swag_from("{}/{}".format(YAML_PATH, "get_icap_info.yml"))
def icap_info():
    return http_msg( get_tb_info(), 200)


@bp_icap.route("/icap/device/id", methods=[GET])
@swag_from("{}/{}".format(YAML_PATH, "get_icap_dev_id.yml"))
def get_device_id():
    return http_msg( { "device_id": app.config.get(KEY_TB_DEVICE_ID) }, 200 )


@bp_icap.route("/icap/device/type", methods=[GET])
@swag_from("{}/{}".format(YAML_PATH, "get_icap_dev_type.yml"))
def get_device_type():
    return http_msg( { "device_type": app.config.get(KEY_DEVICE_TYPE) }, 200 )


@bp_icap.route("/icap/addr", methods=[GET])
@swag_from("{}/{}".format(YAML_PATH, "get_icap_addr.yml"))
def get_addr():
    return http_msg( { "ip" : str(app.config[TB]), "port": str(app.config[TB_PORT]) }, 200 )


@bp_icap.route("/icap/addr", methods=[POST])
@swag_from("{}/{}".format(YAML_PATH, "edit_icap_addr.yml"))
def modify_addr():

    K_IP, K_PORT = "ip", "port"

    # Get data: support form data and json
    data = dict(request.form) if bool(request.form) else request.get_json()

    # Check data
    if data is None:
        msg = 'Get empty data, please make sure the content include "ip" and "port". '
        logging.error(msg)
        return http_msg(msg, 400 )

    # Check ip
    ip = data.get(K_IP)
    if ip is None:
        msg = "Get empty ip address ... "
        logging.error(msg); 
        return http_msg(msg, 400 )
    
    # Check port
    port = data.get(K_PORT)
    if port is None:
        msg = "Get empty port number ... "
        logging.error(msg); 
        return http_msg(msg, 400 )
    
    app.config.update({
        TB: ip,
        TB_PORT: port 
    })
        
    try:
        init_for_icap()
        print('\n\n\n\n\n')
        register_mqtt_event()

        print('\n\n\n\n\n')
        return http_msg( get_tb_info(), 200 )
        
    except Exception as e:
        return http_msg(content = e, status_code = 500 )

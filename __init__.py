# Basic
import os, sys, json, logging

# Flask
from flask import Flask, Blueprint

# Flask - SocketIO
from flask_socketio import SocketIO

# Web API Document for Flask
from flasgger import Swagger

# flask, Corss-Origin Resource Sharing, avoid "No 'Access-Control-Allow-Origin' header"
from flask_cors import CORS as cors

# green flask and application
import eventlet
eventlet.monkey_patch()

# Import Custom Module
from .tools.logger import config_logger
from .tools.common import get_address
from .api.config import config
from .tools.thingsboard import register_tb_device

# MQTT
from flask_mqtt import Mqtt

# Basic Parameters
ENV_CONF_KEY = "IVIT_I"
ENV_CONF = "/workspace/ivit-i.json"

# Basic Function
def init_flask():
    """
    Initailize Flask
        1. Check Environment ( IVIT_I=/path/to/ivit-i.json ).
        2. Initialize Logger.
        3. Initialize Flask App.
        4. Load Flask Configuration form IVIT_I and ./api/config.py.
            - IVIT_I        : let user could modify
            - api/config.py : Internal configuration 
        5. Update HOST in config.
    """

    # check IVIT_I is in environment
    if not (ENV_CONF_KEY in os.environ.keys()):
        if os.path.exists(ENV_CONF):
            os.environ[ENV_CONF_KEY]=ENV_CONF
        else:
            raise KeyError("Could not find the environ \"IVIT_I\", please setup the custom setting path: $ export IVIT_I=/workspace/ivit-i.json")

    # initialize logger
    with open( os.environ[ENV_CONF_KEY], 'r' ) as f:
        data = json.load(f)
        config_logger(log_name=data["LOGGER"], write_mode='a', level='debug', clear_log=True)

    # initialize flask
    app = Flask(__name__)
    app.config.from_object(config)
    app.config.from_file( os.environ[ENV_CONF_KEY], load=json.load )

    # update ip address
    if app.config['HOST'] == "":
        addr = get_address()
        app.config['HOST']=addr
        logging.info('Update HOST to {}'.format(addr))

    return app

def init_for_icap():
    """
    Check if need iCAP

        1. Check configuration
        2. Concatenate URL for thingsboard
        3. Registering thingsboard device
        4. Init MQTT
    """
    mqtt, start_icap = None, app.config["ICAP"]
    logging.info("[ iCAP ] Enable iCAP: {}".format( start_icap ))

    if( start_icap == True ):

        logging.info("[ iCAP ] Enabled iCAP, start to init MQTT and register device ...")
        app.config["MQTT_BROKER_URL"] = app.config["TB"]
        
        # - combine URL
        register_url = "{}:{}{}".format(
            app.config["TB"], 
            app.config["TB_PORT"],
            app.config["TB_API_REG_DEVICE"]
        )
        # - register thingboard device
        ret, (create_time, device_id, device_token) = register_tb_device(register_url)

        if(ret):
            app.config['TB_CREATE_TIME'] = create_time
            app.config['TB_DEVICE_ID'] = device_id
            app.config['TB_TOKEN'] = app.config['MQTT_USERNAME'] = device_token
            
            # - init            
            mqtt = Mqtt(app)

def create_non_exist_folder():
    # creat data folder if it's not exsit
    if not (os.path.exists(app.config["DATA"])):
        os.makedirs(app.config["DATA"])

# Initialize Flask App 
app = init_flask()

# Define Web API docs 
app.config['SWAGGER'] = {
    'title': 'iVIT-I',
    'uiversion': 3
}
swagger = Swagger(app)   

# Define Cross-Origin Resource Sharing - https://www.maxlist.xyz/2020/05/08/flask-cors/
cors(app)                                                       

# Define Socket
socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins='*')   

# Define MQTT For iCAP 
mqtt = init_for_icap()

# Create Folder For iVIT_I
create_non_exist_folder()

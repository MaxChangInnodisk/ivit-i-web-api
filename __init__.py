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

ENV_CONF_KEY = "IVIT_I"
ENV_CONF = "/workspace/ivit-i.json"

def initialize_flask_app():
    """ Initailize Flask App and Get SocketIO Object
    - Return
        - app
        - socketio
        - mqtt
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

    # loading flask configuration
    app.config.from_object(config)
    app.config.from_file( os.environ[ENV_CONF_KEY], load=json.load )

    # update ip address
    if app.config['HOST'] == "":
        addr = get_address()
        app.config['HOST']=addr
        logging.info('Update HOST to {}'.format(addr))

    # define web api docs
    app.config['SWAGGER'] = {
        'title': 'iVIT-I',
        'uiversion': 3
    }
    swagger = Swagger(app)   

    # Init MQTT
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
    else:
        mqtt = None

    # share resource
    cors(app)                                                       

    # define socket
    socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins='*')   

    # do something else
    if not (os.path.exists(app.config["DATA"])):
        # creat data folder if it's not exsit
        os.makedirs(app.config["DATA"])

    # return app,mqtt
    return app, socketio, mqtt

# Initailize Flask App and Get SocketIO Object
app, socketio, mqtt = initialize_flask_app()
# app, mqtt = initialize_flask_app()
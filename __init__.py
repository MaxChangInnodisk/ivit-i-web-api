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

ENV_CONF_KEY = "IVIT_I"
ENV_CONF = "/workspace/ivit-i.json"

def initialize_flask_app():
    """ Initailize Flask App and Get SocketIO Object
    - Return
        - app
        - socketio
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

    # share resource
    cors(app)                                                       
    
    # define socket
    socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins='*')   

    # do something else
    if not (os.path.exists(app.config["DATA"])):
        # creat data folder if it's not exsit
        os.makedirs(app.config["DATA"])

    return app, socketio

# Initailize Flask App and Get SocketIO Object
app, socketio = initialize_flask_app()
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
from .tools import config_logger, get_address
from .api import config

def initialize_flask_app():
    """
    Initailize Flask App and Get SocketIO Object
    ---
    Return
        - app
        - socketio
    """
    # initialize
    app = Flask(__name__)

    # loading configuration
    if not ('IVIT_I' in os.environ.keys()):
        raise KeyError("Could not find the environ \"IVIT_I\", please setup the custom setting path: $ export IVIT_I=/workspace/ivit-i.json")
    else:
        app.config.from_object(config)
        app.config.from_file( os.environ["IVIT_I"], load=json.load )

    # initialize logger
    config_logger(log_name=app.config['LOGGER'], write_mode='a', level='debug', clear_log=True)

    # update ip address
    if app.config['HOST']=="":
        addr = get_address()
        app.config['HOST']=addr
        logging.info('Update HOST to {}'.format(addr))

    # update api docs
    app.config['SWAGGER'] = {
        'title': 'iVIT-I',
        'uiversion': 3
    }

    cors(app)                                                                   # share resource
    socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins='*')   # define socket
    swagger = Swagger(app)                                                      # define web api docs    

    return app, socketio

# Initailize Flask App and Get SocketIO Object
app, socketio = initialize_flask_app()
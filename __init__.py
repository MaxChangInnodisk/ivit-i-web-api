# Basic
import os, sys, json, logging

# Flask
from flask import Flask, Blueprint

# Flask - SocketIO
from flask_sock import Sock

# Web API Document for Flask
from flasgger import Swagger

# flask, Corss-Origin Resource Sharing, avoid "No 'Access-Control-Allow-Origin' header"
from flask_cors import CORS as cors

# Import Custom Module
from .tools.logger import config_logger
from .tools.common import get_address
from .api.config import config

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
cors(app, resources={r"*": {"origins": "*"}})

# Define Socket
sock  = Sock(app)

# Define MQTT For iCAP     
mqtt = Mqtt()

# Create Folder For iVIT_I
create_non_exist_folder()

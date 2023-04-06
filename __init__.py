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
from .api.config import config

# MQTT
from flask_mqtt import Mqtt

# Basic Parameters
ENV_CONF_KEY    = "IVIT_I"
ENV_CONF        = "/workspace/ivit-i.json"

HOST            = "HOST"
TB              = "TB"

def get_all_addr():
    """ Get All Available IP Address """
    from subprocess import check_output
    ips = check_output(['hostname', '--all-ip-addresses']).decode("utf-8").strip()
    ips = ips.split(' ')
    logging.info('Detected available IP Address: {}'.format(ips))
    return ips 

def get_all_addr_by_socket():
    import socket   
    hostname=socket.gethostname()   
    addr=socket.gethostbyname(hostname) 
    logging.info('Using Socket to check the avaiable ip address: {}'.format(addr))
    return addr

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

    # check IVIT_I is in environment variables
    if not (ENV_CONF_KEY in os.environ.keys()):
        assert os.path.exists(ENV_CONF), "Could not find the environ \"IVIT_I\", please setup the custom setting path: $ export IVIT_I=/workspace/ivit-i.json"
        os.environ[ENV_CONF_KEY] = ENV_CONF

    # initialize logger
    with open( os.environ[ENV_CONF_KEY], 'r' ) as f:
        data = json.load(f)
        config_logger(log_name=data["LOGGER"], write_mode='a', level='debug', clear_log=True)

    # initialize flask
    app = Flask(__name__)
    app.config.from_object(config)
    app.config.from_file( os.environ[ENV_CONF_KEY], load=json.load )

    # update AF
    app.config.update({"AF":app.config["FRAMEWORK"]})

    # update ip address
    if app.config.get(HOST) in [ None, "" ]:
        try:
            ips = get_all_addr()
            host_ip = ips[0]
            if not (app.config.get(TB) in [ None, "" ]):
                # if setup icap then compare the first domain is the same
                for ip in ips:
                    if ip.split('.')[0] == app.config.get(TB).split('.')[0]:
                        host_ip = ip

            app.config[HOST] = host_ip
            
        except Exception as e:
            host_ip = get_all_addr_by_socket()
            app.config[HOST] = host_ip
        logging.info('Update HOST to {}'.format(host_ip))
    return app

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
sock  = Sock(app)

# Define MQTT For iCAP 
mqtt = Mqtt()

import logging, subprocess, json, os
from flask import Blueprint, abort, jsonify, current_app, request
from flasgger import swag_from

# Load Module from `web/tools`
from ..tools.parser import get_pure_jsonify
from ..tools.common import get_v4l2, handle_exception, simple_exception, http_msg
from .common import PASS_CODE, FAIL_CODE

YAML_PATH   = "../docs/system"
BP_NAME     = "system"
bp_system = Blueprint(BP_NAME, __name__)

PLATFORM    = "PLATFORM"
NV          = "nvidia"
INTEL       = "intel"
XLNX        = "xilinx"
LOGGER      = "LOGGER"
TXT_EXT     = ".txt"
JSON_EXT    = ".json"

@bp_system.route("/platform", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "platform.yml"))
def get_platform():
    return http_msg( current_app.config[PLATFORM], PASS_CODE )

@bp_system.route("/v4l2", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "v4l2.yml"))
def web_v4l2():
    ret, message = get_v4l2()
    status = PASS_CODE if ret else FAIL_CODE
    return http_msg( message , status)

@bp_system.route("/device", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "device.yml"))
def web_device_info():
    """ Get available devices """
    from ..tools.common import get_devcie_info
    return http_msg(get_devcie_info(), PASS_CODE)

@bp_system.route("/ls_path", methods=["GET"])
@swag_from('{}/{}'.format(YAML_PATH, "ls_path.yml"))
def ls_path():
    _data = request.get_json()
    _path = _data.get('path')
    if _path is None: return 'Excepted content is { "path" : "/path/to/xxx" }', FAIL_CODE
    try:
        return http_msg(os.listdir(_path), PASS_CODE)
    
    except FileNotFoundError as e:
        return http_msg(e, FAIL_CODE)
    
    except Exception as e:
        return http_msg(e, FAIL_CODE)

@bp_system.route("/source", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "source.yml"))
def web_source():
    
    temp_src_config = dict()
    for dev, cnt in current_app.config['SRC'].items():
        temp_src_config[dev] = dict()
        for key, val in cnt.items():
            if key=='object': 
                if val != None or "":
                    temp_src_config[dev][key] = 'source object'
                else:
                    temp_src_config[dev][key] = None
            else:
                temp_src_config[dev].update( {key:val} )
    
    try:
        pure_src_config = get_pure_jsonify( temp_src_config )
        return http_msg(pure_src_config, PASS_CODE)
    
    except Exception as e:
        return http_msg(e, FAIL_CODE)

@bp_system.route("/log", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "log.yml"))
def get_log():
    data = []
    logging.debug("Log path: {}".format(current_app.config[LOGGER]))
    with open( current_app.config[LOGGER], newline='') as f:
        for line in f.readlines():
            data.append( line.rstrip("\n") )
    
    if len(data) >= 1000:
        data = data[(len(data)-1000):]

    return http_msg( data, PASS_CODE )

@bp_system.route("/read_file", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "read_file.yml"))
def read_file():
    """ Read Text and JSON file. """
    data = request.get_json()
    # logging.debug(data)
    path = data["path"]
    try:
        ret_data = []
        name, ext = os.path.splitext(path)
        if ext == TXT_EXT:
            with open( path, 'r') as f:
                for line in f.readlines():
                    ret_data.append(line.strip('\n'))
        if ext == JSON_EXT:
            with open( path, 'r') as f:
                ret_data = json.load(f)
        
        return http_msg( ret_data, PASS_CODE )
    except Exception as e:
        return http_msg( e, FAIL_CODE )
import logging, subprocess, json, os
from flask import Blueprint, abort, jsonify, current_app, request
from flasgger import swag_from

# Load Module from `web/tools`
from ..tools.parser import get_pure_jsonify
from ..tools.common import ( get_v4l2, handle_exception )
from .common import PASS_CODE, FAIL_CODE

YAML_PATH   = "/workspace/ivit_i/web/docs/system"
BP_NAME     = "system"
bp_system = Blueprint(BP_NAME, __name__)

PLATFORM    = "PLATFORM"
NV          = "nvidia"
INTEL       = "intel"
XLNX        = "xilinx"
LOGGER      = "LOGGER"
TXT_EXT     = ".txt"
JSON_EXT    = ".json"

@bp_system.route("/platform")
@swag_from("{}/{}".format(YAML_PATH, "platform.yml"))
def get_platform():
    return jsonify( current_app.config[PLATFORM] ), 200

@bp_system.route("/v4l2/")
@swag_from("{}/{}".format(YAML_PATH, "v4l2.yml"))
def web_v4l2():
    ret, message = get_v4l2()
    status = 200 if ret else 400
    return jsonify( message ), status

@bp_system.route("/device/")
@swag_from("{}/{}".format(YAML_PATH, "device.yml"))
def web_device_info():
    """ Get available devices """
    ret = None
    try:
        from ..tools.common import get_devcie_info
        logging.warning('using get_device_info')
        ret = get_devcie_info()
    except:
        if current_app.config[PLATFORM] == NV:
            from ..tools.common import get_nv_info
            ret = get_nv_info()
            
        elif current_app.config[PLATFORM] == INTEL:
            from ..tools.common import get_intel_info
            ret = get_intel_info()

        elif current_app.config[PLATFORM] == XLNX:
            from ..tools.common import get_xlnx_info
            ret = get_xlnx_info()

    return jsonify(ret)

@bp_system.route("/ls_path", methods=["GET"])
@swag_from('{}/{}'.format(YAML_PATH, "ls_path.yml"))
def ls_path():
    _data = request.get_json()
    _path = _data.get('path')
    if _path is None: return 'Excepted content is { "path" : "/path/to/xxx" }', FAIL_CODE
    try:
        return jsonify(os.listdir(_path)), PASS_CODE
    except FileNotFoundError:
        return "Path not found", FAIL_CODE
    except Exception as e:
        return "Unkown Error ({})".format(handle_exception(e)), FAIL_CODE

@bp_system.route("/source")
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
        return pure_src_config, 200
    except Exception as e:
        return handle_exception(e, "Get source error"), 400

@bp_system.route("/log")
@swag_from("{}/{}".format(YAML_PATH, "log.yml"))
def get_log():
    data = []
    logging.debug("Log path: {}".format(current_app.config[LOGGER]))
    with open( current_app.config[LOGGER], newline='') as f:
        for line in f.readlines():
            data.append( line.rstrip("\n") )
    
    if len(data) >= 1000:
        data = data[(len(data)-1000):]

    return jsonify( data ), 200

@bp_system.route("/read_file/", methods=["POST"])
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
        
        return jsonify( ret_data ), 200
    except Exception as e:
        return handle_exception(error=e, title="Could not load application ... set app to None", exit=False), 400
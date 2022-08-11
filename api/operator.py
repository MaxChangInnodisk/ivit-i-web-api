import shutil
import subprocess as sb
import logging, copy, sys, os
from flask import Blueprint, abort, jsonify, current_app, request
import requests

from .common import get_request_data, print_title

from ..tools.handler import edit_task, add_task, get_tasks, remove_task, import_task
from ..tools.parser import get_pure_jsonify
from ..tools.common import handle_exception

from werkzeug.utils import secure_filename
from flasgger import swag_from

# Define API Docs path and Blue Print
YAML_PATH       = "/workspace/ivit_i/web/docs/operator"
BP_NAME         = "operator"
bp_operators = Blueprint(BP_NAME, __name__)

# Define app config key
AF              = "AF"
TASK_LIST       = "TASK_LIST"
DATA            = "DATA"
TEMP_PATH       = "TEMP_PATH"
INFO            = "info"
TRT             = "tensorrt" 

# Define key for Subprocess
PROC            = "proc"
IMPORT_PROC     = "IMPORT_PROC"
PROC_RUN        = "running"
PROC_DONE       = "done"

# Define key for request data
FRAMEWORK_KEY   = "framework"
SOURCE_KEY      = "source"
THRES_KEY       = "thres"

# Define key for ZIP file from iVIT-T
LABEL_NAME          = "classes"
CLS                 = "cls"
OBJ                 = "obj"
DARKNET             = "darknet"
CLASSIFICATION_KEY  = "classification"
YOLO_KEY            = "yolo"

# Define extension for ZIP file form iVIT-T
DARK_LABEL_EXT  = CLS_LABEL_EXT = ".txt"        # txt is the category list
DARK_JSON_EXT   = CLS_JSON_EXT  = ".json"       # json is for basic information like input_shape, preprocess
DARK_MODEL_EXT  = ".weights"    
DARK_CFG_EXT    = ".cfg"
CLS_MODEL_EXT   = ".onnx"
IR_MODEL_EXT    = ".xml"

# Return Pattern when ZIP file is extracted
NAME            = "name"
PATH            = "path"
TAG             = "tag"
MODEL_PATH      = "model_path"
LABEL_PATH      = "label_path"
CONFIG_PATH     = "config_path"
JSON_PATH       = "json_path"

@bp_operators.after_request
def after_request(response):
    """ When we finish each operation, we have to update the TASK_LIST to get the newest list. """
    logging.info("Updating TASK_LIST, check in '/tasks'")

    try:
        current_app.config[TASK_LIST]=get_tasks()

    except Exception as e:
        err = handle_exception(e)

    return response

@bp_operators.route("/edit/<uuid>", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "edit.yml"))
def edit_event(uuid):

    print_title("Edit {}".format(uuid))
    
    # Get Data and Check
    data = get_request_data()
    
    # Edit Event
    try:
        edit_task(data, uuid)
        return "Edit successed ( {}:{} )".format(uuid, current_app.config['UUID'][uuid]), 200

    except Exception as e:
        return handle_exception(e, "Edit error"), 400

@bp_operators.route("/add/", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "add.yml"))
def add_event():

    print_title("Add Event")
    
    # Get Data and Check
    data = get_request_data()

    # Add event
    try:
        task_status, task_uuid, task_info = add_task(data)
        return jsonify( "Add successed ( {}:{} )".format( data["name"], task_uuid ) ), 200

    except Exception as e:
        return handle_exception(e, "Add error"), 400

def clean_temp_folder():
    if os.path.exists( current_app.config[TEMP_PATH] ):
        shutil.rmtree( current_app.config[TEMP_PATH] )
    os.mkdir( current_app.config[TEMP_PATH] )

def check_import_file_exist(zip_path):
    """remove the old file and direction in target path"""
    
    # Check Zip
    if os.path.exists(zip_path):
        os.remove(zip_path)
    
    # Maybe there has extracted folder, check folder which extracted from ZIP
    task_path = os.path.splitext(zip_path)[0]
    if os.path.exists(task_path):
        shutil.rmtree(task_path)

def get_conversion_table():
    key_cvt_table = {
        CLASSIFICATION_KEY  : CLS,
        YOLO_KEY            : DARKNET if current_app.config[AF] == TRT else OBJ
    }
    return key_cvt_table

def parse_info_from_zip( zip_path ):

    # initialize parameters
    trg_tag = ""
    org_model_path = ""
    trg_model_path = ""
    trg_label_path = ""
    trg_cfg_path = ""
    trg_json_path = ""
    
    # define mapping table
    mapping_table   = get_conversion_table()

    # extract zip file
    task_path = os.path.splitext(zip_path)[0]
    task_name = task_path.split('/')[-1]
    
    sb.run(f"unzip {zip_path} -d {task_path} && rm -rf {zip_path}", shell=True)
    logging.info("Extract to {} and remove {}, found {} files.".format( task_path, zip_path, len(os.listdir(task_path)) ))

    # parse all file 
    for fname in os.listdir(task_path):
        
        fpath = os.path.join(task_path, fname)
        name, ext = os.path.splitext(fpath)

        if ext in [ DARK_MODEL_EXT, CLS_MODEL_EXT, IR_MODEL_EXT ]:
            logging.debug("Detected {}: {}".format("Model", fpath))
            org_model_path = fpath
        
        elif ext in [ DARK_LABEL_EXT, CLS_LABEL_EXT ]:
            logging.debug("Detected {}: {}".format("Label", fpath))
            trg_label_path = fpath
        
        elif ext in [ DARK_JSON_EXT, CLS_JSON_EXT ]:
            logging.debug("Detected {}: {}".format("JSON", fpath))
            trg_json_path = fpath
            
            # update tag name via json file name 
            trg_tag = mapping_table[name.split('/')[-1]]
            
        elif ext in [ DARK_CFG_EXT ]:
            logging.debug("Detected {}: {}".format("Config", fpath))
            trg_cfg_path = fpath

        else:
            logging.debug("Detected {}: {}".format("Meta Data", fpath))

    # It have to convert model if the framework is tensorrt
    convert_proc = None
    if current_app.config[AF]==TRT:
        logging.warning("It have to convert model if the framework is tensorrt")
        
        # capture model name with path which without the extension
        pure_model_name = os.path.splitext(org_model_path)[0]
        trg_model_path = "{}.trt".format( pure_model_name )

        # define command line for convert
        if trg_tag == CLS:    
            cmd = [ "trtexec", 
                    "--onnx={}".format(os.path.realpath(org_model_path)), 
                    "--saveEngine={}".format(os.path.realpath(trg_model_path)) ]
        else:         
            cmd = [ "./converter/yolo-converter.sh",
                    pure_model_name ]
        
        logging.warning("Start to convert tensorrt engine ... {}".format(cmd))
        convert_proc = sb.Popen(cmd, stdout=sb.PIPE)
    
    else:
        trg_model_path = org_model_path

    # update IMPORT_PROC in web api
    key = IMPORT_PROC
    if not ( key in current_app.config ):
        current_app.config.update( { key:dict() } )
    if not ( task_name in current_app.config[key] ):
        current_app.config[key].update( { task_name:dict() })

    current_app.config[key][task_name][PROC]=convert_proc

    # return information
    ret = {
        NAME        : task_name,
        PATH        : task_path,
        TAG         : trg_tag,
        MODEL_PATH  : trg_model_path,
        LABEL_PATH  : trg_label_path,
        CONFIG_PATH : trg_cfg_path,
        JSON_PATH   : trg_json_path
    }

    current_app.config[key][task_name][INFO] = ret

    # log
    logging.info("Finish Parsing ZIP File ... ")
    [ logging.info("    - {}: {}".format(key, val)) for key, val in ret.items() ]

    return ret

@bp_operators.route("/import_zip/", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "extract_zip.yml"))
def import_zip_event():
    """
    1. download ZIP file
    2. extract it and check is 'Classification' or 'Object Detection' ( subprocess.run )
    3. convert model ( background : subprocess.Popen )
    4. return information and successs code
    ---
    Provide web api to check file is convert
    """
    try:
        print_title("Import Event (1) - Extract ZIP from Trainning Tool")
        
        # get file
        file = request.files[SOURCE_KEY]
        file_name = secure_filename(file.filename)
        task_name = os.path.splitext(file_name)[0].split('/')[-1]
        logging.info("Capture file ({})".format(file_name))

        # combine path
        zip_path = os.path.join(current_app.config[TEMP_PATH], file_name)   # temp/aaa.zip
        
        # remove the old file and direction in target path
        check_import_file_exist( zip_path = zip_path )

        # extract zip and remove unused file
        file.save( zip_path )

        # parse information from ZIP file
        info = parse_info_from_zip( zip_path = zip_path )

        return jsonify( info ), 200

    except Exception as e:

        return jsonify(handle_exception(e)), 400

@bp_operators.route("/import_url/", methods=["POST"])
def import_url_event():

    try:
        # get data from web api
        data = dict(request.form) if bool(request.form) else request.get_json()

        # check http head is exist
        http_head = "http://"
        data["url"] = data["url"].strip()
        zip_url = data["url"] if http_head in data["url"] else http_head+data["url"]

        # define temporary zip name
        file_name = "temp.zip"
        zip_path = os.path.join(current_app.config[TEMP_PATH], file_name)
    
        # remove the old file and direction in target path
        check_import_file_exist( zip_path = zip_path )

        
        # create HTTP response object
        logging.warning("Download File from URL ({})".format(zip_url))
        r = requests.get(zip_url)
        
        # send a HTTP request to the server and save
        with open(zip_path, 'wb') as f:
            # r.content -> send a HTTP request to the server
            # f.write -> write the binary contents of the response (r.content) 
            f.write(r.content)

        # parse information from ZIP file
        info = parse_info_from_zip( zip_path = zip_path )

        return jsonify( info ), 200

    except Exception as e:

        return jsonify(handle_exception(e)), 400


@bp_operators.route("/import_proc/", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "import_proc.yml"))
def import_process_default_event():
    ret = copy.deepcopy(current_app.config[IMPORT_PROC])
    return jsonify( get_pure_jsonify( ret ) )

@bp_operators.route("/import_proc/<task_name>/status", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "import_proc_status.yml"))
def import_process_event(task_name):
    
    proc = current_app.config[IMPORT_PROC][task_name][PROC]

    if proc!=None:
        try:
            ret = PROC_RUN if proc.poll() is None else PROC_DONE
        except Exception as e:
            handle_exception(e)
            ret = PROC_DONE
    else:
        ret = PROC_DONE
    return jsonify( ret )

@bp_operators.route("/import/", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "import.yml"))
def import_event():

    print_title("Import Event (2) - Import a Task")
    
    # Get Data and Check
    data = get_request_data()

    # Import event
    try:
        task_status, task_uuid, task_info = import_task(data)
        return jsonify( "Import successed ( {}:{} )".format( data["name"], task_uuid ) ), 200
    except Exception as e:
        current_app.config[TASK_LIST]=get_tasks()
        return handle_exception(e, "Import error"), 400


@bp_operators.route("/remove/", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "remove.yml"))
def remove_application():
    
    data = dict(request.form) if bool(request.form) else request.get_json()
    
    try:
        remove_task(data['uuid'])
        return jsonify('Remove the application ({})'.format(data['uuid'])), 200

    except Exception as e:
        return handle_exception(e, "Remove error"), 400


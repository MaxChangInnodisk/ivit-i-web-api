import shutil
import subprocess as sb
import logging, copy, sys, os
from flask import Blueprint, abort, jsonify, current_app, request

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

@bp_operators.route("/import_1/", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "extract_zip.yml"))
def import_extract_event():
    """
    1. download compress file
    2. uncompress it and check is 'Classification' or 'Object Detection' ( subprocess.run )
    3. convert model ( background : subprocess.Popen )
    4. return information and successs code
    ---
    Provide web api to check file is convert
    """
    print_title("Import Event (1) - Extract ZIP from Trainning Tool")

    # Define the mapping table
    MAP = {
        CLASSIFICATION_KEY  : CLS,
        YOLO_KEY            : DARKNET if current_app.config[AF] == TRT else OBJ
    }
    
    # initialize parameters
    trg_tag = ""
    org_model_path = ""
    trg_model_path = ""
    trg_label_path = ""
    trg_cfg_path = ""
    trg_json_path = ""
    meta_data = []
    
    # get file
    file = request.files[SOURCE_KEY]
    file_name = secure_filename(file.filename)
    task_name = os.path.splitext(file_name)[0]
    logging.info("Capture file ({})".format(file_name))

    # clear && create temp folder
    temp_path = current_app.config[TEMP_PATH]
    if os.path.exists(temp_path):
        shutil.rmtree( temp_path )
    os.mkdir( current_app.config[TEMP_PATH] )
    
    # combine path: ./temp/aaa.zip -> temp/aaa/ -> temp/aaa/export
    zip_path = os.path.join(current_app.config[TEMP_PATH], file_name) # temp/aaa.zip
    task_dir = os.path.dirname( zip_path )                              # temp/
    task_path = os.path.join( task_dir, task_name )                     # temp/aaa

    # remove the old file and direction in target path
    for path in [ zip_path, task_path ]:
        if os.path.exists(path):
            logging.warning("Detected some file ({}), remove the old one ...".format(path))
            if os.path.isfile(path):
                os.remove(path)
            else:
                shutil.rmtree( path )
 
    # extract zip and remove unused file
    file.save( zip_path )
    logging.info("Saving file ({}) and extract it in {}".format(zip_path, task_dir))

    # no export folder 
    sb.run(f"unzip {zip_path} -d {task_path} && rm -rf {zip_path}", shell=True)

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
            trg_tag = MAP[name.split('/')[-1]]
            
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

    # update in web api
    key = IMPORT_PROC
    if not ( key in current_app.config ):
        current_app.config.update( {key:dict()})
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
    current_app.config[key][task_name][INFO]=ret    

    logging.debug(ret)

    return jsonify( ret ), 200

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

@bp_operators.route("/import_2/", methods=["POST"])
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


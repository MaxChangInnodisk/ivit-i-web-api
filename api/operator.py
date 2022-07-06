import shutil
import subprocess as sb
import logging, copy, sys, os
from flask import Blueprint, abort, jsonify, current_app, request
from init_i.web.tools import get_address, get_gpu_info, get_v4l2, edit_task, add_task, get_tasks, remove_task, import_task, get_pure_jsonify
from werkzeug.utils import secure_filename

bp_operators = Blueprint('operator', __name__)

@bp_operators.after_request
def after_request(response):
    logging.info("Updating TASK_LIST, check in '/tasks'")
    try:
        current_app.config["TASK_LIST"]=get_tasks()
    except Exception as e:
        logging.warning(e)
    return response

@bp_operators.route("/edit/<uuid>", methods=["POST"])
def edit_event(uuid):
    """
    """
    # Get data: support form data and json
    data = dict(request.form) if bool(request.form) else request.get_json()

    # Put framework information into data
    if 'framework' not in data.keys(): data.update( {"framework":current_app.config['AF']} )
    # Source: If got new source
    if bool(request.files):
        logging.debug("Get data ...")
        # Saving file
        file = request.files['source']
        file_name = secure_filename(file.filename)
        file_path = os.path.join(current_app.config["DATA"], file_name)
        file.save( file_path )
        # Update data information
        data["source"]=file_path
        
    # Set the format of thres to float
    data["thres"]=float( data["thres"] )
    # Check
    [ logging.debug(cnt) for cnt in ['Check configuration data', '-'*50, data]]
    # Edit task
    try:
        edit_task(data, uuid)
        return "Edit successed ( {}:{} )".format(uuid, current_app.config['UUID'][uuid]), 200
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        logging.error(e)
        return "Edit error: {} ({})".format(e, fname), 400

@bp_operators.route("/add/", methods=["POST"])
def add_event():

    [ logging.info(cnt) for cnt in ['\n', "-"*50, 'Add an application'] ]
    
    # Get data: support form data and json
    data = dict(request.form) if bool(request.form) else request.get_json()

    # Put framework information into data
    if 'framework' not in data.keys(): data.update( {"framework":current_app.config['AF']} )
    # Source: If got new source
    if bool(request.files):
        logging.debug("Get data ...")
        # Saving file
        file = request.files['source']
        file_name = secure_filename(file.filename)
        file_path = os.path.join(current_app.config["DATA"], file_name)
        file.save( file_path )
        # Update data information
        data["source"]=file_path
    
    # Check
    [ logging.debug(cnt) for cnt in ['Check configuration data', '-'*50, data]]
    # Add event
    try:
        task_status, task_uuid, task_info = add_task(data)
        return jsonify( "Add successed ( {}:{} )".format( data["name"], task_uuid ) ), 200
    except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            msg = 'Add Error: \n{}\n{} ({}:{})'.format(exc_type, exc_obj, fname, exc_tb.tb_lineno)
            logging.error(msg)
            return jsonify(msg), 400



@bp_operators.route("/import_1/", methods=["POST"])
def import_extract_event():
    """
    1. download compress file
    2. uncompress it and check is 'Classification' or 'Object Detection' ( subprocess.run )
    3. convert model ( background : subprocess.Popen )
    4. return information and successs code
    ---
    Provide web api to check file is convert
    """
    [ logging.info(cnt) for cnt in ['\n', "-"*50, 'Extract ZIP from Trainning Tool'] ]

    # define key
    LABEL_NAME = "classes"
    DARK_LABEL_EXT = CLS_LABEL_EXT = ".txt"     # txt is the category list
    DARK_JSON_EXT = CLS_JSON_EXT = ".json"      # json is for basic information like input_shape, preprocess

    # darknet format for tensorrt
    DARK_MODEL_EXT = ".weights"    
    DARK_CFG_EXT = ".cfg"

    # onnx format for tensorrt
    CLS_MODEL_EXT = ".onnx"

    # ir model for openvino
    IR_MODEL_EXR = ".xml"

    # define the mapping table
    MAP = {
        "classification": "cls",
        "yolo": "darknet" if current_app.config['AF'] == "tensorrt" else "obj"
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
    file = request.files['source']
    file_name = secure_filename(file.filename)
    task_name = os.path.splitext(file_name)[0]
    logging.info("Capture file ({})".format(file_name))

    # clear && create temp folder
    temp_path = current_app.config["TEMP_PATH"]
    if os.path.exists(temp_path):
        shutil.rmtree( temp_path )
    os.mkdir( current_app.config["TEMP_PATH"] )
    
    # combine path: ./temp/aaa.zip -> temp/aaa/ -> temp/aaa/export
    zip_path = os.path.join(current_app.config["TEMP_PATH"], file_name) # temp/aaa.zip
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

        if ext in [ DARK_MODEL_EXT, CLS_MODEL_EXT, IR_MODEL_EXR ]:
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
    if current_app.config["AF"]=="tensorrt":
        logging.warning("It have to convert model if the framework is tensorrt")
        
        # capture model name with path which without the extension
        pure_model_name = os.path.splitext(org_model_path)[0]
        trg_model_path = "{}.trt".format( pure_model_name )

        # define command line for convert
        if trg_tag == "cls":    
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
    key = "IMPORT_PROC"
    if not ( key in current_app.config ):
        current_app.config.update( {key:dict()})
    if not ( task_name in current_app.config[key] ):
        current_app.config[key].update( { task_name:dict() })
    current_app.config[key][task_name]["proc"]=convert_proc

    # return information
    ret = {
        "name": task_name,
        "path": task_path,
        "tag": trg_tag,
        "model_path": trg_model_path,
        "label_path": trg_label_path,
        "config_path": trg_cfg_path,
        "json_path": trg_json_path
    }
    current_app.config[key][task_name]["info"]=ret    

    logging.debug(ret)

    return jsonify( ret ), 200


@bp_operators.route("/import_proc/", methods=["GET"])
def import_process_default_event():
    ret = copy.deepcopy(current_app.config["IMPORT_PROC"])
    return jsonify( get_pure_jsonify( ret ) )

@bp_operators.route("/import_proc/<task_name>/status", methods=["GET"])
def import_process_event(task_name):
    proc = current_app.config["IMPORT_PROC"][task_name]["proc"]
    if proc!=None:
        try:
            ret = "running" if proc.poll() is None else "done"
        except Exception as e:
            logging.error(e)
            ret = "done"
    else:
        ret = "done"
    return jsonify( ret )

@bp_operators.route("/import_2/", methods=["POST"])
def import_event():

    [ logging.info(cnt) for cnt in ['\n', "-"*50, 'Import an application'] ]
    
    # Get data: support form data and json
    data = dict(request.form) if bool(request.form) else request.get_json()

    # Put framework information into data
    if 'framework' not in data.keys(): data.update( {"framework":current_app.config['AF']} )
    # Source: If got new source
    if bool(request.files):
        logging.debug("Get data ...")
        # Saving file
        file = request.files['source']
        file_name = secure_filename(file.filename)
        file_path = os.path.join(current_app.config["DATA"], file_name)
        file.save( file_path )
        # Update data information
        data["source"]=file_path
    # Check
    [ logging.debug(cnt) for cnt in ['Check configuration data', '-'*50, data]]
    
    # Import event
    try:
        task_status, task_uuid, task_info = import_task(data)
        return jsonify( "Import successed ( {}:{} )".format( data["name"], task_uuid ) ), 200
    except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            msg = 'Import Error: \n{}\n{} ({}:{})'.format(exc_type, exc_obj, fname, exc_tb.tb_lineno)
            logging.error(msg)
            return jsonify(msg), 400


@bp_operators.route("/remove/", methods=["POST"])
def remove_application():
    data = dict(request.form) if bool(request.form) else request.get_json()
    try:
        task_uuid = data['uuid']
        remove_task(task_uuid)
        return jsonify('Remove the application ({})'.format(task_uuid)), 200
    except Exception as e:
        return jsonify('Remove error ({})'.format(e)), 400


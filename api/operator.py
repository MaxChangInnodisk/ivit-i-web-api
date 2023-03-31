import logging, shutil, os, requests, sys, random
import subprocess as sb
import threading
# Flask
from flask import Blueprint, current_app, request
from werkzeug.utils import secure_filename
from flasgger import swag_from

# Common Module
from .common import get_request_data, PASS_CODE, FAIL_CODE

# Handler handle each task and model behaviour
from ..tools.handler import (
    get_tasks, remove_task, add_task, edit_task, 
    init_model, get_model_tag, parse_model_folder, parse_zip_folder
)

from ..tools.parser import (
    get_pure_jsonify
)
from ..tools.common import http_msg

# Define API Docs path and Blue Print
YAML_PATH       = "../docs/operator"
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
XLNX_MODEL_EXT  = ".xmodel"
IR_MODEL_EXT    = ".xml"
IR_MODEL_EXTS   = [ ".bin", ".mapping", ".xml" ]

# Return Pattern when ZIP file is extracted
NAME            = "name"
PATH            = "path"
TAG             = "tag"
MODEL_PATH      = "model_path"
LABEL_PATH      = "label_path"
CONFIG_PATH     = "config_path"
JSON_PATH       = "json_path"

def check_url(url):
    """ Return an available url ( with http ) """
    http_head = "http://"
    if not (http_head in url):
        url = http_head + url
    return url


def check_import_file_exist(zip_path):
    """ Remove the old file and direction in target path"""
    
    # Check Zip
    if os.path.exists(zip_path):
        os.remove(zip_path)
        logging.warning('Detected exist ZIP, auto remove it.')
    
    # Maybe there has extracted folder, check folder which extracted from ZIP
    task_path = os.path.splitext(zip_path)[0]
    if os.path.exists(task_path):
        shutil.rmtree(task_path)
        logging.warning('Detected exist AI Task, auto remove it.')


def capture_process_info(model_tag, proc_name, process, cur_app):
    """ Capture the information of the conversion process """

    logging.warning('Trying to capture convert process ...')

    cls_keywords = {
        "&&&& RUNNING": 0.1,
        "Finish parsing network model": 0.2,
        "[MemUsageChange] Init cuBLAS/cuBLASLt": 0.3,
        "Total Activation Memory": 0.7,
        "Engine built in": 0.9,
        "PASSED TensorRT.trtexec": 1.0
    }

    # yolov4 160, yolov4-tiny 36
    obj_keywords = {
        "Darknet plugins are ready": 0.1,
        "Saving ONNX file...": 0.2,
        "Building ONNX graph...": 0.3,
        "Saving ONNX file": 0.4,
        "Building the TensorRT engine": 0.8,
        "ONNX 2 TensorRT ... Done": 1.0,
    }

    keywords = cls_keywords if model_tag=='cls' else obj_keywords

    send_val, proc_val = 0, 0
    bar_bias = 0.00001
    send_buf, err_list, err_stop_flag = None, [], 'Engine set up failed'

    for line in iter(process.stdout.readline,b''): 
                        
        if process.poll() != None:
            break

        line = line.rstrip().decode() 
        if line.isspace(): 
            proc_val += bar_bias * 0.1 * random.randint(1, 10)
            continue 

        # Check Error
        if '[E]' in line:
            err_list.append(line)
            if err_stop_flag in line:
                with cur_app.app_context():
                    current_app.config[IMPORT_PROC][proc_name].update({
                        "status": 'error',
                        "detail": 'TensorRT Convert Failed !!!'
                    })
                raise RuntimeError('TensorRT Convert Failed ...')

        # Add Process Bar Value
        proc_val += bar_bias * random.randint(1, 10)

        # Check Process Stage
        for keyword in keywords:
            if keyword in line:
                proc_val = keywords[keyword]
                break
        
        # Update Status
        send_val = int(proc_val*100)
        status = f"Converting ({send_val}%)"

        print(f"{status}\n{line}")
        
        # Update Status
        with cur_app.app_context():

            # Web Socket
            # current_app.config["IVIT_WS_POOL"].update({ 
            #     "convertion": line  })
            
            # Convertion Status
            current_app.config[IMPORT_PROC][proc_name].update({
                "status": status,
                "detail": line
            })

    with cur_app.app_context():
        init_model()
        current_app.config[IMPORT_PROC][proc_name].update({
            "status": "Done",
            "detail": line
        })


def update_import_process(model_name:str):
    """ update IMPORT_PROC in config """
    
    key = IMPORT_PROC

    if not ( key in current_app.config ):
        current_app.config.update( { key:dict() } )
    
    if not ( model_name in current_app.config[key] ):
        current_app.config[key].update( { model_name:dict() })

    if not ( PROC in current_app.config[key][model_name]):
        current_app.config[key][model_name].update( { PROC:None })


def convert_model(model_tag:str, model_name:str, model_path:str):
    """ Convert Model
    1. Update import_proc in config
    2. If not nvidia and jetson platform, return model_path and None
    3. Else do conversion
        a. Update trg_model_path
        b. Launch convert command via Popen and store a object call `proc`
        c. Launch thread to capture `proc` and update status to web via websocket
    """

    # update IMPORT_PROC in web api
    update_import_process(model_name)   

    # It have to convert model if the framework is tensorrt
    convert_proc = None
    trg_model_path = model_path

    if current_app.config[AF] != TRT:
        logging.warning('No need to convert !')
        return trg_model_path, convert_proc

    # If need convert
    pure_model_name = os.path.splitext(model_path)[0]
    trg_model_path = "{}.trt".format( pure_model_name )

    # define command line for convert
    if model_tag == CLS:
        logging.warning('Detect Classification Model')
        pla = current_app.config.get('PLATFORM')    
        cmd = [ 
            "trtexec" if pla =='nvidia' else '/usr/src/tensorrt/bin/trtexec', 
            "--onnx={}".format(os.path.realpath(model_path)), 
            "--saveEngine={}".format(os.path.realpath(trg_model_path))
        ]
    else:         
        logging.warning('Detect Object Detection Model')
        cmd = [ "./converter/yolo-converter.sh", pure_model_name ]

    logging.warning("Start to convert tensorrt engine ... {}".format(cmd))        
    
    # Start to Convert
    convert_proc = sb.Popen(cmd, stdout=sb.PIPE, stderr=sb.STDOUT)

    # Start capture conversion stdout
    t = threading.Thread(
        target = capture_process_info, 
        args = ( 
            model_tag,
            model_name, 
            convert_proc, 
            current_app._get_current_object()
        ),
        daemon = True
    ).start()
    
    # Store process object
    current_app.config[IMPORT_PROC][model_name][PROC]=convert_proc
    logging.warning('Updated Convert Process into app.config!!!')
    return trg_model_path, convert_proc


def parse_info_from_zip( zip_path ):
    """ Extract ZIP File and Parsing Informaion from folder """

    logging.info("Start to extract file: {}".format( zip_path ) )
    
    model_name = os.path.splitext(zip_path)[0].split('/')[-1]
    model_path = os.path.join(
        current_app.config['MODEL_DIR'], model_name )

    # Extract zip file
    sb.run(f"unzip -o {zip_path} -d {model_path} && rm -rf {zip_path} && chown 1000:1000 -R .", shell=True)
    logging.info("Extract to {} and remove {}, found {} files.".format( model_path, zip_path, len(os.listdir(model_path)) ))

    # Parsing zip folder
    return parse_zip_folder(model_path)

@bp_operators.route("/add", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "add.yml"))
def add_event():

    logging.info("Add Event")
    
    # Get Data and Check
    data = get_request_data()

    # Add event
    try:
        task_status, task_uuid, task_info = add_task(data)
        return http_msg( f"Add successed !!!( {data['name']}:{task_uuid} )", PASS_CODE )
    
    except Exception as e:
        return http_msg(e, FAIL_CODE)


@bp_operators.route("/edit/<uuid>", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "edit.yml"))
def edit_event(uuid):

    logging.info(f"Edit AI Task: {uuid}")
    
    # Get Data and Check
    data = get_request_data()
    
    # Edit Event
    try:
        edit_task(data, uuid)
        return http_msg( f"Edit success !!!( {uuid}:{current_app.config['UUID'][uuid]} )", PASS_CODE)

    except Exception as e:
        return http_msg(e, FAIL_CODE)


@bp_operators.route("/import_zip", methods=["POST"])
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
        logging.info("Import Event (1) - Extract ZIP from Trainning Tool")
        
        # get file
        file = request.files[SOURCE_KEY]
        file_name = secure_filename(file.filename)
        task_name = os.path.splitext(file_name)[0].split('/')[-1]
        logging.info("Capture file ({})".format(file_name))

        # combine path
        zip_path = os.path.join(current_app.config["MODEL_DIR"], file_name)   # temp/aaa.zip
        
        # remove the old file and direction in target path
        check_import_file_exist( zip_path = zip_path )

        # extract zip and remove unused file
        file.save( zip_path )

        # parse information from ZIP file
        info = parse_info_from_zip( zip_path = zip_path )

        # convert model in background
        new_model_path, proc_name = convert_model(
            model_tag = info['tag'],
            model_path = info['model_path'],
            model_name = info['name'] 
        )
        info['model_path'] = new_model_path

        logging.info(info)

        init_model()

        return http_msg( info, PASS_CODE )

    except Exception as e:
        return http_msg(e, FAIL_CODE)


@bp_operators.route("/import_url", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "extract_url.yml"))
def import_url_event():

    info, status = "", PASS_CODE

    try:
        # get data from web api
        data    = get_request_data()
        
        # check http head is exist
        zip_url     = check_url(data["url"].strip())

        # define temporary zip name
        file_name = "temp.zip"
        zip_path = os.path.join(current_app.config["MODEL_DIR"], file_name)
    
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

        # convert model in background
        new_model_path, proc_name = convert_model(
            model_tag = info['tag'],
            model_path = info['model_path'],
            model_name = info['name'] 
        )
        info['model_path'] = new_model_path

        init_model()

    except Exception as e:
        info, status = e, FAIL_CODE

    finally:
        return http_msg(info, status)


@bp_operators.route("/import_proc", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "import_proc.yml"))
def import_process_default_event():
    
    status, message  = PASS_CODE, ""
    
    if current_app.config.get(IMPORT_PROC)==None:
        return http_msg( 'Import process is not created yet', PASS_CODE )

    try:        
        ret = {}
        for key in list(current_app.config[IMPORT_PROC].keys()):
            cur_proc = current_app.config[IMPORT_PROC][key].get('proc')
            cur_proc_mod = None if cur_proc is None else cur_proc.__module__
            cur_proc_inf = current_app.config[IMPORT_PROC][key].get('info')

            ret.update({ key: {
                'proc': cur_proc_mod,
                'info': cur_proc_inf
            } })
            
        message = get_pure_jsonify( ret )

    except Exception as e:
        status, message  = FAIL_CODE, e

    return http_msg(message, status)


@bp_operators.route("/import_proc/<task_name>", methods=["GET"])
@bp_operators.route("/import_proc/<task_name>/status", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "import_proc_status.yml"))
def import_process_event(task_name):

    if current_app.config.get(IMPORT_PROC)==None:
        return http_msg( 'Import process is not created yet', PASS_CODE )

    try:
        proc = current_app.config[IMPORT_PROC][task_name][PROC]
        status = current_app.config[IMPORT_PROC][task_name].get('status', PROC_RUN)
    
    except Exception as e:
        return http_msg(e, FAIL_CODE)

    if proc == None:
        return http_msg(PROC_DONE, PASS_CODE)

    if proc.poll() != None:
        return http_msg(PROC_DONE, PASS_CODE)

    return http_msg(status, PASS_CODE)

@bp_operators.route("/import", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "import.yml"))
def import_event():
    """ 匯入任務
    由於 import_zip 跟 import_url 已經把 zip 解壓縮並存放了
    所以這邊就像是 加入任務 一樣
    """
    logging.info("Import a Task")
    status, message = PASS_CODE, ""
    
    # Import event
    try:
        # Convert data to json format
        data = get_request_data()
    
        # Import Task Event
        task_status, task_uuid, task_info = add_task(data)
        
        message = "Import successed ( {}:{} )".format( data["name"], task_uuid )
        
    except Exception as e:
        status, message = FAIL_CODE, e
        logging.exception(e)
        
    finally:
        current_app.config[TASK_LIST]=get_tasks()
        return http_msg(message, status)


@bp_operators.route("/remove", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "remove.yml"))
def remove_application():
    
    status, message = PASS_CODE, ""
    
    try:
        # Convert data to json format
        data = get_request_data()

        # Return state and message
        remove_task(data['uuid'])
        
        # Setup information
        message = "Remove Task ({}) Successed!".format(data['uuid'])
    
    except Exception as e:
        message, status = e, FAIL_CODE

    finally:

        current_app.config[TASK_LIST]=get_tasks()
        
        return http_msg(message, status)


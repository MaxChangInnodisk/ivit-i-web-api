from flask import abort, request
import cv2, time, logging, base64, threading, os, sys, copy, json
from werkzeug.utils import secure_filename

from .. import socketio, app

# from ..ai.pipeline import Source
# from ivit_i.utils.utils import handle_exception
from ivit_i.common.pipeline import Source
from ivit_i.utils.utils import handle_exception

# Define app config key
AF              = "AF"
TASK_LIST       = "TASK_LIST"
DATA            = "DATA"
TEMP_PATH       = "TEMP_PATH"
PROC            = "proc"
IMPORT_PROC     = "IMPORT_PROC"
TRT             = "tensorrt" 

# Define key for request data
FRAMEWORK_KEY   = "framework"
SOURCE_KEY      = "source"
THRES_KEY       = "thres"

# Define key for ZIP file from iVIT-T
LABEL_NAME      = "classes"
CLS             = "cls"
OBJ             = "obj"
DARKNET         = "darknet"
CLASSIFICATION_KEY  = "classification"
YOLO_KEY            = "yolo"

# Define extension for ZIP file form iVIT-T
DARK_LABEL_EXT  = CLS_LABEL_EXT = ".txt"        # txt is the category list
DARK_JSON_EXT   = CLS_JSON_EXT  = ".json"       # json is for basic information like input_shape, preprocess

## Darknet format for tensorrt
DARK_MODEL_EXT  = ".weights"    
DARK_CFG_EXT    = ".cfg"

## onnx format for tensorrt
CLS_MODEL_EXT   = ".onnx"

## ir model for openvino
IR_MODEL_EXT    = ".xml"


# Define Status
RUN         = "run"
STOP        = "stop"
ERROR       = "error"
STATUS      = "status"

# Define Key which in app.config
TASK        = "TASK"
TASK_LIST   = "TASK_LIST"
UUID        = "UUID"
TAG         = "tag"

# Define Key which declared in app.config[SRC]
SRC         = "SRC"
OBJECT      = "object"
TYPE        = "type"
PROC        = "proc"

# Define Key which declared in each task
FRAMEWORK   = "framework"
CONFIG      = "config"
LABEL_PATH  = "label_path"
APPLICATION = "application"
MODEL       = "model"
NAME        = "name"
SOURCE      = "source"
SOURCE_TYPE = "source_type"
DEVICE      = "device"
STATUS      = "status"
THRES       = "thres"
START_TIME  = "start_time"
DETS        = "detections"


# Define AI Inference Parameters
API         = "api"
RUNTIME     = "runtime"
DRAW_TOOLS  = "draw_tools"
PALETTE     = "palette"
FRAME_IDX   = "frame_index"
STREAM      = "stream"

# Define SocketIO Event
IMG_EVENT   = "images"
RES_EVENT   = "results"

# Define SocketIO Parameters
IDX         = "idx"
INFER       = "inference"
FPS         = "fps"
FIRST_TIME  = "first_time_flag"
LIVE_TIME   = "live_time"
G_TEMP      = "gpu_temp"
G_LOAD      = "gpu_load"

RET_INFO = {
    IDX         : None,
    DETS        : None,
    INFER       : None,
    FPS         : None,
    LIVE_TIME   : None,
    G_TEMP      : None,
    G_LOAD      : None,
}

# Define Stream Type
RTSP        = 'rtsp'
VIDEO       = 'video'
BASE64_EXT  = '.jpg'
BASE64_DEC  = "utf-8"
PASS_CODE   = 200
FAIL_CODE   = 400

# Brand & Framework Info
NV          = "nvidia"
TRT         = "tensorrt"
INTEL       = "intel"
OV          = "openvino"
XLNX        = "xilinx"
VTS         = "vitis-ai"

def get_request_file(save_file=False):
    """
    Get request file
     - Argument
        - save_file
            - type: bool
            - desc: set True if need to save file
     - Output
        - file name/path
            - type: String
            - desc: return file path if save_file is True, on the other hand, return name
    """
    
    file        = request.files[SOURCE_KEY]
    file_name   = secure_filename(file.filename)
    
    if save_file:
        try:
            file_path = os.path.join(app.config[DATA], secure_filename(file_name))

            file.save( file_path )
        except Exception as e:
            err = handle_exception(e, "Error when saving file ...")
            abort(404, {'message': err } )

        return file_path
    
    return file_name

def get_request_data():
    """ Get data form request and parse content. """
    # Support form data and json
    data = dict(request.form) if bool(request.form) else request.get_json()

    # Put framework information into data
    if FRAMEWORK_KEY not in data.keys(): 
        data.update( { FRAMEWORK_KEY : app.config[AF] } )

    # Source: If got new source
    if bool(request.files):
        file_path = get_request_file(save_file=True)
        data[SOURCE_KEY] = file_path
        logging.debug("Get data ({})".format(data[SOURCE_KEY]))
        
    # Set the format of thres to float
    if THRES_KEY in data:
        data[THRES_KEY]=float( data[THRES_KEY].strip() )
        logging.debug("Convert data[{}] to float format".format(THRES_KEY))
    
    # Print out to check information
    print_data(data)

    return data

def print_title(title):
    logging.info( "{}\n{}".format('-' * 3, title) )

def print_data(data, title='Check request data'):
    logging.debug(title)
    [ logging.debug(" - {}: {}".format(key, val)) for key, val in data.items() ]

def frame2btye(frame):
    """
    Convert the image with numpy array format to btye ( base64 )

    - Arguments
        - frame
            - type: numpy.array
    - Output
        - ret
            - type: dict
            - parameters
                - image
                    - type: btye
                    - desc: the image which format is btye
                - height
                    - type: int
                    - desc: the orginal image height
                - width
                    - type: int
                    - desc: the orginal image width
                - channel
                    - type: int
                    - desc: the orginal image channel
    """
    ret, (h,w,c) = None, frame.shape
    frame_base64 = base64.encodebytes(
        cv2.imencode('.jpg', frame)[1].tobytes()
    ).decode("utf-8")

    ret = {
        "image"     : frame_base64,
        "height"    : h,
        "width"     : w,
        "channel"   : c
    }
    return ret

def get_src(task_uuid, reload_src=False):
    """ 
    Setup the source object and run 

    - Arguments
        - task_uuid
            - type: string
        - reload_src
            - type: bool
            - desc: reset the source object
    - Output
        - source_object
            - type: object
            - desc: the source object same with app.config["SRC"][{src_name}][object]
    """
    # get the target source name
    logging.debug("Get Source Name")
    src_name = app.config[TASK][task_uuid][SOURCE]
    
    # if source is None or reload_src==True then create a new source
    try:
        src_obj = app.config[SRC][src_name][OBJECT]
    except Exception as e:
        raise (handle_exception(e))

    if ( src_obj == None ) or reload_src:
        logging.info('Initialize a new source.')
        try: 
            app.config[SRC][src_name][OBJECT] = Source(src_name, app.config[SRC][src_name][TYPE])
        except Exception as e:
            handle_exception(e)
            raise (handle_exception(e))
    
    # setup status and error message in source config
    status, err = app.config[SRC][src_name][OBJECT].get_status()
    app.config[SRC][src_name][STATUS], app.config[SRC][src_name][ERROR] = RUN if status else ERROR, err
    
    # return object
    return app.config[SRC][src_name][OBJECT]

def stop_src(task_uuid, release=False):
    """ 
    Stop the source and release it if needed, but if the source still be accesed by process, then it won't be stopped. 
    
    - Argument
        - task_uuid
            - type: string
        - release
            - type: bool
            - desc: release the source object
    """
    
    # initialize
    src_name, stop_flag, access_proc = app.config[TASK][task_uuid][SOURCE], True, []
    
    # checking all process
    for _uuid in app.config[SRC][src_name][PROC]:
        
        if _uuid in app.config[TASK].keys():
            
            # if any task with same source is still running, then set stop_flag to False
            if ( task_uuid!=_uuid) and (app.config[TASK][_uuid][STATUS]==RUN): 
                access_proc.append(_uuid)
                stop_flag = False           
        else:
            # clean unused uuid
            app.config[SRC][src_name][PROC].remove(_uuid)
    
    # clear source object
    if stop_flag:
        logging.info('Stopping source object ...')
        app.config[SRC][src_name][STATUS] = STOP

        if app.config[SRC][src_name][OBJECT] != None: 
            # need release source
            if release:
                logging.warning('Release source ...')
                app.config[SRC][src_name][OBJECT].release() 
                app.config[SRC][src_name][OBJECT] = None 
            else:
                app.config[SRC][src_name][OBJECT].stop()
        logging.info('Stop the source.')
    else:
        logging.warning("Stop failed, source ({}) accessed by {} ".format(src_name, access_proc))

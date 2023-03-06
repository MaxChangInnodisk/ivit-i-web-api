import cv2, time, logging, base64, threading, os, copy, sys, json
from flask import Blueprint, abort, jsonify, app, request
from werkzeug.utils import secure_filename
from flasgger import swag_from

# Load Module from `web/api`
from .common import frame2btye, get_src, stop_src, stop_task_thread, check_uuid_in_config
from .common import sock, app
from ..tools.common import handle_exception, simple_exception, http_msg, json_exception
from ..tools.handler import get_tasks
from ..tools.parser import get_pure_jsonify
from ..ai.get_api import get_api

# Get Application Module From iVIT-I
sys.path.append(os.getcwd())
from ivit_i.common.pipeline import Source, Pipeline
from ivit_i.utils.err_handler import InferenceError, ApplicationError

# Legacy
from ivit_i.app.handler import get_application

# New
from ivit_i.app.handler import ivitAppHandler

# Define API Docs yaml
YAML_PATH   = ""
BP_NAME     = "stream"
DIV         = "-" * 20
YAML_PATH   = "../docs/stream"
bp_stream   = Blueprint(BP_NAME, __name__)

# Define Status
RUN         = "run"
STOP        = "stop"
ERROR       = "error"
STATUS      = "status"

# Define Key which in app.config
TASK        = "TASK"
TASK_LIST   = "TASK_LIST"
UUID        = "UUID"
APP_DIR     = "APP_DIR"

TAG         = "tag"

# Define Key which declared in app.config[SRC]
SRC         = "SRC"
OBJECT      = "object"
TYPE        = "type"
PROC        = "proc"

# Define Key which declared in each task
AF = FRAMEWORK   = "framework"
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

# Define Socket Event
INFER_WS_POOL   = "INFER_WS_POOL"
IVIT_WS_POOL    = "IVIT_WS_POOL"

SYS_POOL    = "SYS_POOL"
IMG_EVENT   = "images"
RES_EVENT   = "results"
IVIT_EVENT   = "ivit"

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
FAIL_CODE   = 500

# Brand & Framework Info
PLATFORM    = "PLATFORM"
NV          = "nvidia"
TRT         = "tensorrt"
INTEL       = "intel"
OV          = "openvino"
XLNX        = "xilinx"
VTS         = "vitis-ai"

# def send_socketio(frame, socketio, namespace):
#     # Convert to base64 format
#     frame_base64 = base64.encodebytes(cv2.imencode(BASE64_EXT, frame)[1].tobytes()).decode(BASE64_DEC)
#     # Send socketio to client
#     socketio.emit(IMG_EVENT, frame_base64, namespace=namespace)

def define_gst_pipeline(src_wid, src_hei, src_fps, rtsp_url, platform='intel'):
    base = 'appsrc is-live=true block=true format=GST_FORMAT_TIME ' + \
            f'caps=video/x-raw,format=BGR,width={src_wid},height={src_hei},framerate={src_fps}/1 ' + \
            ' ! videoconvert ! video/x-raw,format=I420 ' + \
            ' ! queue' + \
            ' ! x264enc bitrate=4096 speed-preset=0 key-int-max=20' + \
            f' ! rtspclientsink location={rtsp_url}'

    xlnx =  'videomixer name=mix sink_0::xpos=0 sink_0::ypos=0 ! omxh264enc prefetch-buffer=true ' + \
            'control-rate=2 target-bitrate=3000 filler-data=false constrained-intra-prediction=true ' + \
            'periodicity-idr=120 gop-mode=low-delay-p aspect-ratio=3 low-bandwidth=true default-roi-quality=4 ' + \
            '! video/x-h264,alignment=au ' + \
            f'! rtspclientsink location={rtsp_url} ' + \
            'appsrc ' + \
            f'caps=video/x-raw,format=BGR,width={src_wid},height={src_hei},framerate={src_fps}/1 ' + \
            '! videoconvert ! mix.sink_0'

    maps = {
        'intel': base,
        'nvidia': base,
        'jetson': base,
        'xilinx': xlnx
    }
    logging.info(f'Parse {platform} Gstreamer Pipeline ')
    return maps.get(platform)

# AI Inference Thread
# -----------------------------------------------

def stream_task(task_uuid, src, namespace):
    '''
    Stream event: sending 'image' and 'result' to '/app/<uuid>/stream' via socketio
    
    - Arguments
        - task_uuid
        - src
        - namespace
    '''
    
    # Prepare Parameters
    ret_info, info  = dict(), None
    model_conf      = app.config[TASK][task_uuid][CONFIG]
    trg             = app.config[TASK][task_uuid][API]
    platform        = app.config[PLATFORM]
    app_dir         = app.config[APP_DIR]
    temp_model_conf = copy.deepcopy(model_conf)

    # Setup Application
    try:

        #NOTE: r1.1 still keep the legacy application usage
        
        # Custom Application using ivitAppHandler
        app_handler = ivitAppHandler()
        app_handler.register_from_folder(app_dir.replace('./', ''))
        if temp_model_conf['application']['name'] in app_handler.get_all_apps():
            app_object  = app_handler.get_app(temp_model_conf['application']['name'])
            application = app_object(
                params  = temp_model_conf,
                label   = temp_model_conf[ temp_model_conf['framework'] ]['label_path'] )
        
        # Defualt application
        else:
            application = get_application(temp_model_conf)

    # If setup application failed
    except Exception as e: 
        
        err_mesg = handle_exception(e)
        stop_task_thread(task_uuid, json_exception(e))
        
        # Runtime Error Message
        err_mesg.update({
            'uuid': task_uuid,
            'stop_task': True
        })
        app.config[IVIT_WS_POOL].update({
            "error": err_mesg
        })
        raise RuntimeError( err_mesg )
    
    # Async Mode
    trg.set_async_mode()

    # Define RTSP pipeline
    src_name    = app.config[TASK][task_uuid][SOURCE]
    (src_hei, src_wid), src_fps = src.get_shape(), src.get_fps()

    # Define RTSP
    rtsp_url = f"rtsp://localhost:8554/{task_uuid}"
    gst_pipeline = define_gst_pipeline(
        src_wid, src_hei, src_fps, rtsp_url, platform
    )
    out = cv2.VideoWriter(  gst_pipeline, cv2.CAP_GSTREAMER, 0, 
                            src_fps, (src_wid, src_hei), True )

    logging.info('Gstreamer Pipeline: {}\n\n{}'.format(gst_pipeline, rtsp_url))

    # if not out.isOpened():
    #     raise Exception("can't open video writer")

    # start looping
    cur_info, temp_info, app_info = None, None, None
    cur_fps, fps_pool = 30, []
    temp_socket_time = 0
    try:

        while(app.config[SRC][src_name][STATUS]==RUN):
            
            t1 = time.time()

            # Get the frame from source
            success, frame = src.read()   
             
            # Check frame
            if not success:
                if src.get_type() == 'v4l2': 
                    raise RuntimeError('USB Camera Error')
                else:
                    application.reset()
                    src.reload()
                    continue    
                                
            # If got frame then add the frame index
            app.config[TASK][task_uuid][FRAME_IDX] += 1
            
            t2 = time.time()

            # Copy frame for drawing
            draw = frame.copy()

            # Start to Inference and update info
            cur_info = trg.inference( frame )

            # Update temp_info
            if(cur_info is not None):
                if cur_info.get(DETS) is not None:
                    temp_info = cur_info

            t3 = time.time()

            # Draw something
            if (temp_info is not None):
                draw, app_info = application(draw, temp_info)

            # Send RTSP
            out.write(draw)

            # Select Information to send
            info = temp_info.get(DETS) if (temp_info is not None) else ''


            # Combine the return information
            ret_info = {
                IDX         : int(app.config[TASK][task_uuid][FRAME_IDX]),
                DETS        : info,
                INFER       : round((t3-t2)*1000, 3),
                FPS         : cur_fps,
                LIVE_TIME   : round((time.time() - app.config[TASK][task_uuid][START_TIME]), 5),
            }
            # Send Information
            if(time.time() - temp_socket_time >= 1):                
                app.config[INFER_WS_POOL].update({ task_uuid: json.dumps(get_pure_jsonify(ret_info)) })
                temp_socket_time = time.time()

            # Delay to fix in 30 fps
            t_cost, t_expect = (time.time()-t1), (1/src_fps)
            time.sleep(t_expect-t_cost if(t_cost<t_expect) else 1e-5)
            
            # Update Live Time and FPS
            app.config[TASK][task_uuid][LIVE_TIME] = int((time.time() - app.config[TASK][task_uuid][START_TIME]))
            
            # Average FPS
            if(cur_info):
                fps_pool.append(int(1/(time.time()-t1)))
                cur_fps = sum(fps_pool)//len(fps_pool) if len(fps_pool)>10 else cur_fps
                 
        logging.info('Stop streaming')

    except Exception as e:
        err_mesg = handle_exception(e)
        stop_task_thread(task_uuid, err_mesg)
        raise RuntimeError(err_mesg)
    
    finally:
        trg.release()

# -----------------------------------------------
# Define Threading Hook
# def thread_custom_hook(args):
    
    


# -----------------------------------------------
# Define Sock Event
@sock.route(f'/{IVIT_EVENT}')
def ivit_message(sock):
    """ 
    Send websocket every 0.01 second, 
    the websocket content parsing from `app.config[INFER_WS_POOL]`
    
    To avoid inference data duplicated, 
    we will check the preview data and current data is the same
    """
    temp_data = None
    while(True):
        cur_data = json.dumps(app.config[IVIT_WS_POOL])
        if temp_data != cur_data:
            sock.send( cur_data )
            temp_data = cur_data
            time.sleep(33e-3)

        time.sleep(0.01)

# Define Sock Event
@sock.route(f'/{RES_EVENT}')
def message(sock):
    """ 
    Send websocket every 0.01 second, 
    the websocket content parsing from `app.config[INFER_WS_POOL]`
    
    To avoid inference data duplicated, 
    we will check the preview data and current data is the same
    """
    temp_data = None
    while(True):
        cur_data = json.dumps(app.config[INFER_WS_POOL])
        if temp_data != cur_data:
            sock.send( cur_data )
            temp_data = cur_data
            time.sleep(33e-3)

        time.sleep(0.01)

@bp_stream.route("/update_src", methods=["POST"])
@swag_from("{}/{}".format(YAML_PATH, "update_src.yml"))
def update_src():
    """ Get the first frame when upload a new file """

    # Get data: support form data and json
    data = dict(request.form) if bool(request.form) else request.get_json()
    
    # Source: If got new file
    if bool(request.files):
        # Saving file
        file = request.files[SOURCE]
        file_name = secure_filename(file.filename)
        file_path = os.path.join(app.config["DATA"], file_name)
        file.save( file_path )
        # Update data information
        data[SOURCE]=file_path

    # Check If the source is already exist 
    if data[SOURCE] in app.config[SRC]:

        # If exist and initialize
        src = app.config[SRC][data[SOURCE]].get(OBJECT)
        if src is not None:
            ret = None

            # If Alive
            if src.t.is_alive():
                ret = src.get_first_frame()
            
            # Not Alive
            else:
                src.start()
                ret = src.get_first_frame()
                src.stop()
                src.release()

            # Return Frame
            if ret:
                return frame2btye(ret), PASS_CODE

    # If not exist then create a new Source
    src = Pipeline( data[SOURCE], data[SOURCE_TYPE] )
    src.set_cam(height=720, width=1280, fps=30)
    try:
        src.start()
        
        ret = src.get_first_frame()
        src.release()
        return frame2btye(ret), PASS_CODE
    except Exception as e:
        return http_msg(e, FAIL_CODE)

@bp_stream.route("/task/<uuid>/get_frame")
@swag_from("{}/{}".format(YAML_PATH, "get_frame.yml"))
def get_first_frame(uuid):
    """ Get target task first frame via web api """

    # ----------------------------------------------------------
    # Checking UUID
    try:
        check_uuid_in_config(uuid)
    except Exception as e:
        return http_msg(e, FAIL_CODE)
    
    src = get_src(uuid)
    ret = frame2btye(src.get_first_frame())
    # return '<img src="data:image/jpeg;base64,{}">'.format(frame_base64)
    return http_msg( ret, PASS_CODE )
    
@bp_stream.route("/task/<uuid>/stream/start", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "stream_start.yml"))
def start_stream(uuid):      

    title_msg = lambda title: f'{title}, Stream (WebRTC): /task/{uuid}/stream , Log (WebSocket): "/task/results", RTSP: rtsp://{app.config["HOST"]}:8554/{uuid}.'
    try:
        # ----------------------------------------------------------
        # Checking UUID
        check_uuid_in_config(uuid)
    
        [ logging.info(cnt) for cnt in [DIV, f'Start stream ... destination of socket event: "/task/{uuid}/stream"', DIV] ]
        
        # ----------------------------------------------------------
        # Create New Stream Thread
        if app.config[TASK][uuid][STREAM] is None:

            app.config[TASK][uuid][STREAM] = threading.Thread(
                target  = stream_task, 
                args    = (uuid, get_src(uuid), f'/task/{uuid}/stream', ), 
                name    = f"{uuid}",
                daemon  = True
            )
            
            while(app.config[TASK][uuid][STREAM] is None):
                print('waitting ...')
                time.sleep(1) # wait for thread
            
            logging.info('Created a new stream thread ( {} )'.format(app.config[TASK][uuid][STREAM]))
        
        # ----------------------------------------------------------
        # Or No Need to Create  
        if app.config[TASK][uuid][STREAM].is_alive():
            msg = title_msg("Stream is running")
            logging.info(msg)
            return http_msg(msg, PASS_CODE)
        
        # ----------------------------------------------------------
        # Start a stream thread
        app.config[TASK][uuid][STREAM].start()
        msg = title_msg("Stream is started")
        logging.info(msg)

        return http_msg(msg, PASS_CODE)

    except Exception as e:
        # ----------------------------------------------------------
        # Clear Thread
        msg = "Something wrong when starting stream thread ... ({}) ".format(
                    handle_exception(e)
        )
        if app.config[TASK][uuid][STREAM] is not None:  
            if app.config[TASK][uuid][STREAM].is_alive():
                os.kill(app.config[TASK][uuid][STREAM])
                
        logging.warning(msg)
        return http_msg(e, FAIL_CODE)
    
@bp_stream.route("/task/<uuid>/stream/stop", methods=["GET"])
@swag_from("{}/{}".format(YAML_PATH, "stream_stop.yml"))
def stop_stream(uuid):

    # ----------------------------------------------------------
    # Checking UUID
    try:
        check_uuid_in_config(uuid)
    except Exception as e:
        return http_msg(e, FAIL_CODE)

    if app.config[TASK][uuid][STATUS]==ERROR:
        return http_msg('Stream Error ! ', FAIL_CODE)
        
    if app.config[TASK][uuid][STREAM]!=None:
        try:
            src_name = app.config[TASK][uuid][SOURCE]
            app.config[SRC][src_name][STATUS] = STOP
            
            app.config[TASK][uuid][STREAM].join()
            logging.warning('Stopped stream !')
        except Exception as e:
            logging.warning(e)

    app.config[TASK][uuid][STREAM]=None
    logging.warning('Clear Stream ...')
    return http_msg('Stop stream success ! ', 200)

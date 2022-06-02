# ------------------------------------------------------------------------------------------
# common module
import cv2, time, logging, shutil, subprocess, base64, threading, os, sys, copy, json

# flask basic, socketio, filename and docs ( flasgger )
from flask import Flask, Blueprint, jsonify, request, render_template, url_for, redirect, abort
from flask_socketio import SocketIO
from werkzeug.utils import secure_filename
from flasgger import Swagger
# flask, Corss-Origin Resource Sharing, avoid "No 'Access-Control-Allow-Origin' header"
from flask_cors import CORS as cors
# green flask and application
import eventlet
eventlet.monkey_patch()  

# init_i 
sys.path.append(os.getcwd())
from init_i.utils.logger import config_logger
from init_i.web.utils import get_address, get_tasks, get_pure_jsonify
from init_i.web.api import basic_setting, bp_utils, bp_tasks, bp_tests, bp_operators
# ------------------------------------------------------------------------------------------
from init_i.web.ai.pipeline import Source
try:
    from init_i.web.ai.tensorrt import trt_init as init
    from init_i.web.ai.tensorrt import trt_inference as do_inference
except Exception as e:
    raise Exception(e)
DIV = "*"*20
def create_app():
    
    # initialize
    app = Flask(__name__)
    
    # loading configuration
    if not ('INIT_I' in os.environ.keys()):
        raise KeyError("Could not find the environ \"INIT_I\", please setup the custom setting path: $ export INIT_I=/workspace/init-i.json")
    else:
        app.config.from_object(basic_setting)
        app.config.from_file( os.environ["INIT_I"], load=json.load )

    # define logger
    config_logger(log_name=app.config['LOGGER'], write_mode='a', level='debug', clear_log=True)

    # update ip address
    if app.config['HOST']=="":
        addr = get_address()
        app.config['HOST']=addr
        logging.info('Update HOST to {}'.format(addr))

    cors(app)                                                                   # share resource
    socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins='*')   # define socket
    swagger = Swagger(app)                                                      # define web api docs

    # register blueprint
    app.register_blueprint(bp_tasks)        # captrue the info of tasks
    app.register_blueprint(bp_operators)    # operate the task
    app.register_blueprint(bp_utils)        # some utils, like 'v4l2', 'device' ... etc
    app.register_blueprint(bp_tests)        # just for test
    
    # check data folder is exsit
    if not (os.path.exists(app.config["DATA"])):
        os.makedirs(app.config["DATA"])

    # define the web api
    @app.before_first_request
    @app.route("/reset/")
    def first_time():
        """ loading the tasks at first time or need to reset, the uuid and relatived information will be generated at same time."""
        logging.info("Start to initialize task and generate uuid for each task ... ")
        
        [ app.config[key].clear() for key in [ "TASK", "UUID", "TASK_LIST", "APPLICATION" ] if key in app.config ]
                
        try:
            app.config["TASK_LIST"]=get_tasks(need_reset=True)
            return app.config["TASK_LIST"], 200
        except Exception as e:
            return "Initialize Failed ({})".format(e), 400

    @app.before_request
    def before_request():
        # request.remote_addr, request.method, request.scheme, request.full_path, response.status
        if not ("favicon.ico" in request.path):
            logging.info("{} {} {} from {}".format(request.method, request.path, request.scheme, request.remote_addr))

    @app.route("/", methods=["GET"])
    def index():
        """ return task list """
        return jsonify(app.config["TASK_LIST"])

    @app.route("/routes/", methods=["GET", "POST"])
    def help():
        routes = {}
        for r in app.url_map._rules:
            routes[r.rule] = {}
            routes[r.rule]["functionName"] = r.endpoint
            routes[r.rule]["methods"] = list(r.methods)

        routes.pop("/static/<path:filename>")
        return jsonify(routes)

    @app.route("/<key>/", methods=["GET"])
    def return_config(key):
        key_lower, key_upper = key.lower(), key.upper()
        ret = None
        if key_lower in app.config.keys():
            ret = app.config[key_lower]
        elif key_upper in app.config.keys():
            ret = app.config[key_upper]
        else:
            return "Unexcepted Route ( Please check /routes )", 400
        return jsonify( get_pure_jsonify(ret) ), 200

    def run_src(uuid, reload_src=False):
        src_name = app.config['TASK'][uuid]['source']

        # if source is None then create a new source
        if (app.config['SRC'][src_name]['object']==None) or reload_src:
            app.config['SRC'][src_name]['object'] = Source(src_name, app.config['SRC'][src_name]['type'])
            logging.info('Initialize a new source.')
        
        status, err = app.config['SRC'][src_name]['object'].get_status()
        
        logging.debug('Checking running source status and err: {}, {}'.format(status, err))
        
        app.config['SRC'][src_name]['status'] = 'run' if status else 'error'
        app.config['SRC'][src_name]['error'] = err
        logging.info('Set the status of source to `run`.')

    def stop_src(uuid, rel=False):

        # Check all application is stop
        src_name = app.config['TASK'][uuid]['source']
        clear_src = True
        # If any task with same source is still running, then not clear source object
        for _uuid in app.config['SRC'][src_name]["proc"]:
            if uuid==_uuid:
                continue
            if (_uuid in app.config['TASK'].keys()):
                if app.config['TASK'][_uuid]['status']=='run': 
                    logging.warning("Still have task store the source ... ")
                    clear_src = False
            else:
                app.config['SRC'][src_name]["proc"].remove(_uuid)

        if clear_src:
            app.config['SRC'][src_name]['status'] = 'stop'

            if app.config['SRC'][src_name]['object'] != None: 
                app.config['SRC'][src_name]['object'].release() if rel else app.config['SRC'][src_name]['object'].stop()
            if rel:
                app.config['SRC'][src_name]['object'] = None
            logging.info('Stop the source.')
        else:
            logging.info(f'The {src_name} is still been accessed ...')

    def get_src(uuid, init=False, reload_src=False):
        if init: run_src(uuid, reload_src)
        src_object = app.config['SRC'][ app.config['TASK'][uuid]['source'] ]['object']
        logging.warning(type(src_object))
        return src_object

    def stream(uuid, src, namespace):
        '''Stream event: sending 'image' and 'result' to '/app/<uuid>/stream' via socketio'''
        ret_info, info = dict(), None
        # get all the ai inference objects
        [ model_conf, trg, runtime, draw, palette ] = [ app.config['TASK'][uuid][key] for key in ['config', 'api', 'runtime', 'draw_tools', 'palette'] ]
        # deep copy the config to avoid changing the old one when do inference
        temp_model_conf = copy.deepcopy(model_conf)
        # start looping
        try:
            while(app.config['SRC'][app.config['TASK'][uuid]['source']]['status']=='run'):
                # logging.debug('get frame')
                t1 = time.time()
                ret_frame, frame = src.get_frame()
                app.config['TASK'][uuid]['frame_index'] += 1
                # If no frame, wait a new frame when source type is rtsp and video
                if not ret_frame: 
                    logging.debug('Reconnect source ... ')
                    if src.get_type().lower() in ['rtsp', 'video']:
                        src = get_src(uuid, init=True, reload_src=True) 
                        continue
                    else:
                        err_msg ="Couldn't get the frame data."
                        app.config['SRC'][ app.config['TASK'][uuid]['source'] ]['error']= err_msg
                        app.config['TASK'][uuid]['error']= err_msg
                        app.config['TASK'][uuid]['status']= 'error'
                        break
                # Check is all ai object is exist
                # logging.debug('check object')
                if (None in [ temp_model_conf, trg, runtime, draw, palette ]):
                    logging.error('None in [ temp_model_conf, trg, runtime, draw, palette ]')
                    break
                
                # logging.debug('do inference ( frame:{} ) '.format(app.config['TASK'][uuid]['frame_index']))
                t2 = time.time()
                ret, info, _frame = do_inference( frame, uuid, temp_model_conf, trg, runtime, draw, palette, ret_draw=True ) 
                frame = _frame if ret else frame
    
                # logging.debug('convert to base64')
                t3 = time.time()
                frame_base64 = base64.encodebytes(cv2.imencode('.jpg', frame)[1].tobytes()).decode("utf-8")
                
                # logging.debug('update information')
                ret_info = {
                    'idx': app.config['TASK'][uuid]['frame_index'],
                    'detections': info["dets"] if info is not None else None,
                    'inference': round((t3-t2)*1000, 3),
                    'fps': int(1/( time.time() - t1 )),
                    'live_time': int((time.time() - app.config['TASK'][uuid]['start_time'])),
                    'gpu_temp': "",
                    'gpu_load': ""
                }
                # emit( event_name, event_content, event_namespace )
                logging.debug('Send socketio to namespace: {}'.format(namespace))
                socketio.emit('images', frame_base64, namespace=namespace)#,broadcast=True)
                socketio.emit('results', get_pure_jsonify(ret_info, json_format=False), namespace=namespace)#, broadcast=True)
                socketio.sleep(0)

                # logging.debug('Updaet live time')
                app.config['TASK'][uuid]['live_time'] = int((time.time() - app.config['TASK'][uuid]['start_time'])) 
            
            logging.info('Stop streaming')
        except Exception as e:
            logging.error('Stream Error: {}'.format(e))

        logging.info('Stop streaming')

    @app.route("/task/<uuid>/run", methods=["GET"])
    def run_task(uuid):
        # check if the task is ready to inference
        if app.config['TASK'][uuid]['status']=='error':
            return 'The task is not ready, here is the error messages: {}'.format( 
                app.config['TASK'][uuid]['error'] ), 400

        if app.config['TASK'][uuid]['status']=='run':
            return 'The task is still running ... ', 200

        # get target platform and initailize AI model
        af = app.config['TASK'][uuid]['framework']
        tag = app.config['TASK'][uuid]['config']['tag']
        
        # create a source object if it is not exist
        src = get_src(uuid, init=True)        
        src_status, src_err = src.get_status()
        if not src_status:
            logging.error('get source error')
            app.config['TASK'][uuid]['err_error']=src_err
            return src_err, 400
        
        # Using deep copy to avoid changing the configuration data during initailization ( init)
        temp_config = copy.deepcopy(app.config['TASK'][uuid]['config']) 
        # store object in app.config
        
        # if using openvino and tag is pose we have to send a 
        ai_objects = init(temp_config, src.get_frame()[1]) if af=='openvino' and tag=='pose' else init(temp_config)
        
        # if no object then return error message
        # ai_objects = error message if initialize failed
        if None in ai_objects:
            msg = '{}\n( {} )'.format( ai_objects[0], "Auto restart the service" )    
            logging.critical(msg)
            return msg, 400
        else:
            (   app.config['TASK'][uuid]['api'], 
                app.config['TASK'][uuid]['runtime'], 
                app.config['TASK'][uuid]['draw_tools'], 
                app.config['TASK'][uuid]['palette']  ) = ai_objects
        
        # send socketio and update app.config
        app.config['TASK'][uuid]['status'] = "run"
        
        # create stream object
        if app.config['TASK'][uuid]['stream']==None:

            app.config['TASK'][uuid]['stream'] = threading.Thread(
                target=stream, 
                args=(uuid, src, f'/task/{uuid}/stream' ), 
                name=f"{uuid}")
            app.config['TASK'][uuid]['stream'].daemon = True

        # set initialize time
        app.config['TASK'][uuid]['start_time']=time.time()
        app.config['TASK'][uuid]['live_time']=0
        app.config['TASK'][uuid]['first_time_flag']=True
        
        # set frame information
        app.config['TASK'][uuid]['frame_index']=0

        # update list
        app.config["TASK_LIST"]=get_tasks()

        return 'Run Application ({}) ! The results is display in /task/<uuid>/stream'.format(uuid), 200

    @app.route("/task/<uuid>/stop", methods=["GET"])
    def stop_task(uuid):
        logging.info("Stopping stream ...")
        try:
            stop_src(uuid, rel=True)
            for key in ['api', 'runtime', 'palette']:
                logging.debug(" - setting {} to None".format(key))
                app.config['TASK'][uuid][key] = None
            
            app.config['TASK'][uuid]['status']="stop"
            logging.info( f"Stoping stream ({uuid})" )
            # update list
            app.config["TASK_LIST"]=get_tasks()
            return "Stop {}".format(uuid), 200
        except Exception as e:
            return f"{e}", 400
        
    @app.route("/task/<uuid>/stream/start", methods=["GET"])
    def start_stream(uuid):      

        af = app.config['AF']
        [ logging.info(cnt) for cnt in [DIV, f'Start stream ... destination of socketio event: "/task/{uuid}/stream"', DIV] ]

        if app.config['TASK'][uuid]['stream'] == None:
            logging.info('Create a new thread')
            app.config['TASK'][uuid]['stream'] = threading.Thread(  
                target=stream,
                args=(uuid, get_src(uuid, init=True), f'/task/{uuid}/stream'), 
                name=f"{uuid}"
            )
        if not app.config['TASK'][uuid]['stream'].is_alive():
            try:
                app.config['TASK'][uuid]['stream'].start()
                logging.info('Stream is created')
                return jsonify('Stream is created')
            except Exception as e:
                logging.error('Start thread error: {}'.format(e))
                return jsonify('Start thread error: {}'.format(e)), 500
        else:
            logging.info('Stream is running')
            return jsonify('Stream is running'), 200

    @app.route("/task/<uuid>/stream/stop", methods=["GET"])
    def stop_stream(uuid):

        if app.config['TASK'][uuid]['status']!='error':
            stop_src(uuid)
            if app.config['TASK'][uuid]['stream']!=None:
                # if app.config['TASK'][uuid]['stream'].is_alive():
                try:
                    app.config['TASK'][uuid]['stream'].join()
                except Exception as e:
                    logging.warning(e)
                app.config['TASK'][uuid]['stream']=None
        return jsonify('Stop source ... ')

    return app, socketio

if __name__ == "__main__":
    
    app, socketio = create_app()
    socketio.run(app, host=app.config['HOST'], port=app.config['PORT'], debug=app.config['DEBUG'])

else:
    # export INIT_I=/workspace/init-i.json
    app, socketio = create_app()
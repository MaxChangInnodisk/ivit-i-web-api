# ------------------------------------------------------------------------------------------
# common module
import cv2, time, logging, shutil, subprocess, base64, threading, os, sys, copy, json
# ------------------------------------------------------------------------------------------
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
# ------------------------------------------------------------------------------------------
# ivit_i 
sys.path.append(os.getcwd())
from ivit_i.utils.logger import config_logger
from ivit_i.web.tools import get_address, get_tasks, get_pure_jsonify
from ivit_i.web.api import config, bp_system, bp_tasks, bp_operators, bp_application
# ------------------------------------------------------------------------------------------
from ivit_i.web.ai.pipeline import Source
from ivit_i.web.ai.get_api import get_api
from ivit_i.app.handler import get_application
# ------------------------------------------------------------------------------------------
DIV = "*"*20
# ------------------------------------------------------------------------------------------

def create_app():
    
    # initialize
    app = Flask(__name__)
    
    # loading configuration
    if not ('IVIT_I' in os.environ.keys()):
        raise KeyError("Could not find the environ \"IVIT_I\", please setup the custom setting path: $ export IVIT_I=/workspace/ivit-i.json")
    else:
        app.config.from_object(config)
        app.config.from_file( os.environ["IVIT_I"], load=json.load )

    # define logger
    config_logger(log_name=app.config['LOGGER'], write_mode='a', level='debug', clear_log=True)

    # update ip address
    if app.config['HOST']=="":
        addr = get_address()
        app.config['HOST']=addr
        logging.info('Update HOST to {}'.format(addr))

    # update api docs
    app.config['SWAGGER'] = {
        'title': 'iVIT-I',
        'uiversion': 3
    }
    
    cors(app)                                                                   # share resource
    socketio = SocketIO(app, async_mode="eventlet", cors_allowed_origins='*')   # define socket
    swagger = Swagger(app)                                                      # define web api docs    

    # register blueprint
    app.register_blueprint(bp_tasks)        # captrue the info of tasks
    app.register_blueprint(bp_operators)    # operate the task
    app.register_blueprint(bp_system)        # some utils, like 'v4l2', 'device' ... etc
    app.register_blueprint(bp_application)
    
    # check data folder is exsit
    if not (os.path.exists(app.config["DATA"])):
        os.makedirs(app.config["DATA"])

    # define the web api
    @app.before_first_request
    @app.route("/reset/")
    def first_time():
        # """ loading the tasks at first time or need to reset, the uuid and relatived information will be generated at same time."""
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
        # """ return task list """
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
            return f"Unexcepted Route ({key}), Please check /routes.", 400
        return jsonify( get_pure_jsonify(ret) ), 200

    def run_src(task_uuid, reload_src=False):
        # """ setup the source object and run """
        # get the target source name
        src_name = app.config['TASK'][task_uuid]['source']
        # if source is None or reload_src==True then create a new source
        if (app.config['SRC'][src_name]['object']==None) or reload_src:
            app.config['SRC'][src_name]['object'] = Source(src_name, app.config['SRC'][src_name]['type'])
            logging.info('Initialize a new source.')
        # setup status and error message in source config
        status, err = app.config['SRC'][src_name]['object'].get_status()
        app.config['SRC'][src_name]['status'], app.config['SRC'][src_name]['error'] = 'run' if status else 'error', err
        # return object
        return app.config['SRC'][src_name]['object']

    def stop_src(task_uuid, rel=False):
        """ stop the source and release it if needed, but if the source still be accesed by process, then it won't be stopped. """
        # initialize
        src_name, stop_flag, access_proc = app.config['TASK'][task_uuid]['source'], True, []
        # checking all process
        for _uuid in app.config['SRC'][src_name]["proc"]:
            if _uuid in app.config['TASK'].keys():
                # if any task with same source is still running, then set stop_flag to False
                if ( task_uuid!=_uuid) and (app.config['TASK'][_uuid]['status']=='run'): 
                    access_proc.append(_uuid)
                    stop_flag = False           
            else:
                # clean unused uuid
                app.config['SRC'][src_name]["proc"].remove(_uuid)
        # clear source object
        if stop_flag:
            logging.info('Stopping source object ...')
            app.config['SRC'][src_name]['status'] = 'stop'
            if app.config['SRC'][src_name]['object'] != None: 
                # need release source
                if rel:
                    logging.warning('Release source ...')
                    app.config['SRC'][src_name]['object'].release() 
                    app.config['SRC'][src_name]['object'] = None 
                else:
                    app.config['SRC'][src_name]['object'].stop()
            logging.info('Stop the source.')
        else:
            logging.warning("Stop failed, source ({}) accessed by {} ".format(src_name, access_proc))
        
    def get_src(task_uuid, reload_src=False):
        """ get source object """
        return run_src(task_uuid, reload_src)

    def stream_task(task_uuid, src, namespace, infer_function):
        '''Stream event: sending 'image' and 'result' to '/app/<uuid>/stream' via socketio'''
        ret_info, info = dict(), None
        # get all the ai inference objects
        do_inference = infer_function
        [ model_conf, trg, runtime, draw, palette ] = [ app.config['TASK'][task_uuid][key] for key in ['config', 'api', 'runtime', 'draw_tools', 'palette'] ]
        # deep copy the config to avoid changing the old one when do inference
        temp_model_conf = copy.deepcopy(model_conf)

        has_application=False
        try:
            application = get_application(temp_model_conf)
            if application == None:
                has_application = False
            else:
                has_application = True
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            msg = 'Application Error: \n{}\n{} ({}:{})'.format(exc_type, exc_obj, fname, exc_tb.tb_lineno)
            logging.error(msg)
            has_application = False
        
        # start looping
        try:
            while(app.config['SRC'][app.config['TASK'][task_uuid]['source']]['status']=='run'):
                # logging.debug('get frame')
                t1 = time.time()
                ret_frame, frame = src.get_frame()
                app.config['TASK'][task_uuid]['frame_index'] += 1

                # If no frame, wait a new frame when source type is rtsp and video
                if not ret_frame: 
                    logging.debug('Reconnect source ... ')
                    if src.get_type().lower() in ['rtsp', 'video']:
                        src = get_src(task_uuid, reload_src=True) 
                        continue
                    else:
                        err_msg ="Couldn't get the frame data."
                        app.config['SRC'][ app.config['TASK'][task_uuid]['source'] ]['error']= err_msg
                        app.config['TASK'][task_uuid]['error']= err_msg
                        app.config['TASK'][task_uuid]['status']= 'error'
                        break
                
                # Check is all ai object is exist
                # logging.debug('check object')
                if (None in [ temp_model_conf, trg, runtime, draw, palette ]):
                    logging.error('None in [ temp_model_conf, trg, runtime, draw, palette ]')
                    break
                
                # logging.debug('do inference ( frame:{} ) '.format(app.config['TASK'][task_uuid]['frame_index']))
                t2 = time.time()
                org_frame = frame.copy()

                ret, info, frame_draw = do_inference(   
                    org_frame, task_uuid, temp_model_conf, 
                    trg, runtime, draw, palette, ret_draw=(not has_application) ) 
    
                # replace the frame generated from application function
                if ret and has_application :
                    frame_draw = application(org_frame, info)

                # logging.debug('convert to base64')
                t3 = time.time()
                frame_base64 = base64.encodebytes(cv2.imencode('.jpg', frame_draw)[1].tobytes()).decode("utf-8")
                
                # logging.debug('update information')
                ret_info = {
                    'idx': app.config['TASK'][task_uuid]['frame_index'],
                    'detections': info["detections"] if info is not None else None,
                    'inference': round((t3-t2)*1000, 3),
                    'fps': int(1/( time.time() - t1 )),
                    'live_time': int((time.time() - app.config['TASK'][task_uuid]['start_time'])),
                    'gpu_temp': "",
                    'gpu_load': ""
                }
                # emit( event_name, event_content, event_namespace )
                # logging.debug('Send socketio to namespace: {}'.format(namespace))
                socketio.emit('images', frame_base64, namespace=namespace)#,broadcast=True)
                socketio.emit('results', get_pure_jsonify(ret_info, json_format=False), namespace=namespace)#, broadcast=True)
                socketio.sleep(0)

                # logging.debug('Updaet live time')
                app.config['TASK'][task_uuid]['live_time'] = int((time.time() - app.config['TASK'][task_uuid]['start_time'])) 
            
            logging.info('Stop streaming')
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            msg = 'Stream Error: \n{}\n{} ({}:{})'.format(exc_type, exc_obj, fname, exc_tb.tb_lineno)
            logging.error(msg)
            return jsonify(msg), 400

    @app.route("/update_src/", methods=["POST"])
    def update_src():
        
        # Get data: support form data and json
        data = dict(request.form) if bool(request.form) else request.get_json()

        # Source: If got new source
        if bool(request.files):
            # Saving file
            file = request.files['source']
            file_name = secure_filename(file.filename)
            file_path = os.path.join(app.config["DATA"], file_name)
            file.save( file_path )
            # Update data information
            data["source"]=file_path

        src = Source(input_data=data["source"], intype=data["source_type"])
        ret_frame = src.get_first_frame()
        h,w,c = ret_frame.shape
        frame_base64 = base64.encodebytes(cv2.imencode('.jpg', ret_frame)[1].tobytes()).decode("utf-8")
        
        return jsonify( { "image":frame_base64 , "height": h, "width": w} )

    @app.route("/task/<uuid>/get_frame")
    def get_first_frame(uuid):
        src = get_src(uuid)
        ret_frame = src.get_first_frame()
        h,w,c = ret_frame.shape
        frame_base64 = base64.encodebytes(cv2.imencode('.jpg', ret_frame)[1].tobytes()).decode("utf-8")
        # return '<img src="data:image/jpeg;base64,{}">'.format(frame_base64)
        return jsonify( { "image":frame_base64 , "height": h, "width": w} )

    @app.route("/task/<uuid>/run/", methods=["GET"])
    def run_task(uuid):
        # check if the task is ready to inference
        if app.config['TASK'][uuid]['status']=='error':
            return 'The task is not ready, here is the error messages: {}'.format( 
                app.config['TASK'][uuid]['error'] ), 400
        if app.config['TASK'][uuid]['status']=='run':
            return 'The task is still running ... ', 200
        
        # create a source object if it is not exist
        src = get_src(uuid)        
        src_status, src_err = src.get_status()
        if not src_status:
            logging.error('get source error')
            app.config['TASK'][uuid]['error']=src_err
            return src_err, 400
        
        # avoid changing the configuration data during initailization ( init)
        temp_config = copy.deepcopy(app.config['TASK'][uuid]['config']) 
        
        # get ai objects
        init, do_inference = get_api()
        if (app.config['TASK'][uuid]['framework']=='openvino') and (app.config['TASK'][uuid]['config']['tag']=='pose'):
            ai_objects = init(temp_config, src.get_frame()[1]) 
        else:
            ai_objects = init(temp_config)
        
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
        
        # set initialize time
        app.config['TASK'][uuid]['start_time']=time.time()
        app.config['TASK'][uuid]['live_time']=0
        app.config['TASK'][uuid]['first_time_flag']=True
        
        # set frame information
        app.config['TASK'][uuid]['frame_index']=0

        # update list
        app.config["TASK_LIST"]=get_tasks()

        return jsonify('Run Application ({}) ! The results is display in /task/<uuid>/stream'.format(uuid)), 200

    @app.route("/task/<uuid>/stop/", methods=["GET"])
    def stop_task(uuid):
        # """ Stop the task: release source, set relative object to None, set task status to stop, reload task list """
        try:
            logging.info("Stopping task ...")
            # stop source and release source
            stop_src(uuid, rel=True)
            # set relative object to None
            for key in ['api', 'runtime', 'palette', 'stream']:
                logging.debug(" - setting app.config[TASK][<uuid>][{}] to None".format(key))
                app.config['TASK'][uuid][key] = None
            # set the status of task to 'stop'
            app.config['TASK'][uuid]['status']="stop"
            # update list
            app.config["TASK_LIST"]=get_tasks()
            # msg
            msg = f"Stop the task ({uuid})"
            logging.info( msg )
            return jsonify( msg ), 200

        except Exception as e:
            return jsonify(f"{e}"), 400
        
    @app.route("/task/<uuid>/stream/start/", methods=["GET"])
    def start_stream(uuid):      

        [ logging.info(cnt) for cnt in [DIV, f'Start stream ... destination of socketio event: "/task/{uuid}/stream"', DIV] ]

        # create stream object
        _, do_inference = get_api()
        if app.config['TASK'][uuid]['stream']==None:
            app.config['TASK'][uuid]['stream'] = threading.Thread(
                target=stream_task, 
                args=(uuid, get_src(uuid), f'/task/{uuid}/stream', do_inference ), 
                name=f"{uuid}",
            )
            app.config['TASK'][uuid]['stream'].daemon = True
        # check if thread is alive
        if app.config['TASK'][uuid]['stream'].is_alive():
            logging.info('Stream is running')
            return jsonify('Stream is running'), 200
        try:
            app.config['TASK'][uuid]['stream'].start()
            logging.info('Stream is created')
            return jsonify('Stream is created'), 200
        except Exception as e:
            logging.error('Start thread error: {}'.format(e))
            return jsonify('Start thread error: {}'.format(e)), 400


    @app.route("/task/<uuid>/stream/stop/", methods=["GET"])
    def stop_stream(uuid):

        if app.config['TASK'][uuid]['status']!='error':
            stop_src(uuid)
            if app.config['TASK'][uuid]['stream']!=None:
                # if app.config['TASK'][uuid]['stream'].is_alive():
                try:
                    logging.warning('Stopping stream ...')
                    app.config['TASK'][uuid]['stream'].join()
                except Exception as e:
                    logging.warning(e)
            app.config['TASK'][uuid]['stream']=None
            return jsonify('Stop stream success ! '), 200

    return app, socketio

if __name__ == "__main__":
    
    app, socketio = create_app()
    socketio.run(app, host=app.config['HOST'], port=app.config['PORT'], debug=app.config['DEBUG'])

else:
    # export IVIT_I=/workspace/ivit-i.json
    app, socketio = create_app()
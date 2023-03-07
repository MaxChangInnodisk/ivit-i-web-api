import cv2, time, logging, os, sys, copy, json, threading
from flask import jsonify, request

# ivit_i 
sys.path.append(os.getcwd())
from ivit_i.utils import handle_exception
from ivit_i.app.handler import ivitAppHandler
# web api
from .api.system import bp_system
from .api.task import bp_tasks
from .api.operator import bp_operators
from .api.application import bp_application
from .api.stream import bp_stream
from .api.icap import bp_icap, init_for_icap, register_mqtt_event
from .api.model import bp_model

from .tools.parser import get_pure_jsonify
from .tools.handler import get_tasks

DIV         = "*" * 20
TASK        = "TASK"
UUID        = "UUID"
TASK_LIST   = "TASK_LIST"
APPLICATION = "APPLICATION"
ICO         = "favicon.ico"

IVIT_WS_POOL = "IVIT_WS_POOL"

APP_CTRL    = "APP_CTRL"
APP_DIR     = "APP_DIR"

def create_app():
    
    from . import app, sock, mqtt

    # create basic folder
    for path in ["TEMP_PATH", "DATA"]:
        trg_path = app.config[path]
        if not os.path.exists(trg_path):
            logging.warning("Create Folder: {}".format(trg_path))
            os.mkdir(trg_path)

    # register blueprint
    app.register_blueprint(bp_tasks)        # captrue the info of tasks
    app.register_blueprint(bp_operators)    # operate the task
    app.register_blueprint(bp_system)        # some utils, like 'v4l2', 'device' ... etc
    app.register_blueprint(bp_application)
    app.register_blueprint(bp_stream)
    app.register_blueprint(bp_icap)
    app.register_blueprint(bp_model)
    
    # define the web api
    # @app.before_first_request
    @app.route("/reset")
    def first_time():
        # Init Task
        with app.app_context():
            for key in [ TASK, UUID, TASK_LIST, APPLICATION ]:
                if key in app.config:
                    app.config[key].clear()    
            app.config[TASK_LIST]=get_tasks(need_reset=True)
        return "Reset ... Done", 200
        
    @app.before_request
    def before_request():
        # request.remote_addr, request.method, request.scheme, request.full_path, response.status
        if not (ICO in request.path):
            logging.info("{} {} {} from {}".format(request.method, request.path, request.scheme, request.remote_addr))

    @app.route("/", methods=["GET"])
    def index():
        # """ return task list """
        return jsonify(app.config[TASK_LIST])

    @app.route("/routes/", methods=["GET", "POST"])
    def help():
        routes = {}
        for r in app.url_map._rules:
            routes[r.rule] = {}
            routes[r.rule]["functionName"] = r.endpoint
            routes[r.rule]["methods"] = list(r.methods)

        routes.pop("/static/<path:filename>")
        return jsonify(routes)

    # @app.route("/<key>", methods=["GET"])
    # def return_config(key):
    #     key_lower, key_upper = key.lower(), key.upper()
    #     ret = None
    #     if key_lower in app.config.keys():
    #         ret = app.config[key_lower]
    #     elif key_upper in app.config.keys():
    #         ret = app.config[key_upper]
    #     else:
    #         return f"Unexcepted Route ({key}), Please check /routes.", 400
    #     return jsonify( get_pure_jsonify(ret) ), 200

    # Init Task
    with app.app_context():
        for key in [ TASK, UUID, TASK_LIST, APPLICATION ]:
            if key in app.config:
                app.config[key].clear()    
        app.config[TASK_LIST]=get_tasks(need_reset=True)
    
    # For iCAP
    try:
        init_for_icap()
        
        register_mqtt_event()
        
    except Exception as e:
        handle_exception(e)
        pass

    # For ivitApp
    app.config[APP_CTRL] = ivitAppHandler()
    
    # Clear path, the ivitAppHandler must to pure address
    app.config[APP_CTRL].register_from_folder( app.config[APP_DIR] )

    # Init WebSocket Event
    @sock.route("/ivit")
    def ivit_mesg(sock):
        """ 
        Define iVIT System Message
        
        'error': {
            'type' : '',
            'status_code': 0,
            'message': 'xxx',
            'uuid': 'xxx',
            'stop_task': True
        }
        """
        while(True):
            
            if app.config[IVIT_WS_POOL]=={}:
                # Send daat
                sock.send(app.config[IVIT_WS_POOL])
                # Clear data
                app.config[IVIT_WS_POOL].clear()

            time.sleep(33e-3)
            

    logging.info("Finish Initializing.")
    return app, sock

if __name__ == "__main__":
    
    app, sock = create_app()
    # sock.run(app, host=app.config['HOST'], port=app.config['PORT'], debug=app.config['DEBUG'])
    app.run(host=app.config['HOST'], port=app.config['PORT'], debug=app.config['DEBUG'])

else:
    # export IVIT_I=/workspace/ivit-i.json
    app, sock = create_app()
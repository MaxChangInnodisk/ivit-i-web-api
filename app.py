import cv2, time, logging, os, sys, copy, json
from flask import jsonify, request

# ivit_i 
sys.path.append(os.getcwd())

from ivit_i.web.api.system import bp_system
from ivit_i.web.api.task import bp_tasks
from ivit_i.web.api.operator import bp_operators
from ivit_i.web.api.application import bp_application
from ivit_i.web.api.stream import bp_stream

from .tools.parser import get_pure_jsonify
from .tools.handler import get_tasks
from .tools.common import handle_exception

DIV         = "*" * 20
TASK        = "TASK"
UUID        = "UUID"
TASK_LIST   = "TASK_LIST"
APPLICATION = "APPLICATION"
ICO         = "favicon.ico"

def create_app():
    
    from . import app, socketio

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
    
    # define the web api
    @app.before_first_request
    @app.route("/reset/")
    def first_time():
        # """ loading the tasks at first time or need to reset, the uuid and relatived information will be generated at same time."""
        logging.info("Start to initialize task and generate uuid for each task ... ")
        
        for key in [ TASK, UUID, TASK_LIST, APPLICATION ]:
            if key in app.config:
                app.config[key].clear()
                
        try:
            app.config[TASK_LIST]=get_tasks(need_reset=True)
            return app.config[TASK_LIST], 200
        except Exception as e:
            handle_exception(e)
            return "Initialize Failed ({})".format(e), 400

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

    return app, socketio

if __name__ == "__main__":
    
    app, socketio = create_app()
    socketio.run(app, host=app.config['HOST'], port=app.config['PORT'], debug=app.config['DEBUG'])

else:
    # export IVIT_I=/workspace/ivit-i.json
    app, socketio = create_app()
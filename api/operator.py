import logging, copy, sys, os
from flask import Blueprint, abort, jsonify, current_app, request
from init_i.web.tools import get_address, get_gpu_info, get_v4l2, edit_task, add_task, get_tasks, remove_task
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

@bp_operators.route("/remove/", methods=["POST"])
def remove_application():
    data = dict(request.form) if bool(request.form) else request.get_json()
    try:
        task_uuid = data['uuid']
        remove_task(task_uuid)
        return jsonify('Remove the application ({})'.format(task_uuid)), 200
    except Exception as e:
        return jsonify('Remove error ({})'.format(e)), 400
import logging, copy
from flask import Blueprint, abort, jsonify, current_app, render_template
from init_i.web.utils import get_address, get_gpu_info, get_v4l2

bp_tests = Blueprint('test', __name__)

@bp_tests.route("/test/")
def testing():
    try:
        asdsdasd()
    except Exception as e:
        return f"{e}", 400

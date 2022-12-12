import sys, os, time, copy, logging
from flask import Blueprint, current_app
sys.path.append(os.getcwd())
from ivit_i.common import api
from ivit_i.utils.err_handler import handle_exception

# ------------------------------------------------------------------------
# Vitis-AI
""" 初始化 Vitis-AI """
def vitis_init(prim_conf, first_frame=None):
    logging.info('Init Vitis-AI')
    try:
        if 'obj' in prim_conf['tag']:
            from ivit_i.obj.yolov3 import YOLOv3 as trg
        if "cls" in prim_conf['tag']:
            from ivit_i.cls.classification import Classification as trg
        
        trg = api.get(prim_conf)
        trg.load_model(prim_conf, 1)
        trg.set_async_mode()

    except Exception as e:
        raise Exception(handle_exception(e))
    return trg

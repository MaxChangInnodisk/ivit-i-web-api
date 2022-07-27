import logging
from flask import Blueprint, current_app
import sys, os, time, copy
import numpy as np

sys.path.append(os.getcwd())
try:
    from ivit_i.utils.drawing_tools import Draw as trt_draw
    from ivit_i.utils.drawing_tools import get_palette, draw_fps
    from ivit_i.common import api
except Exception as e:
    msg='Can not import TensorRT ... {}'.format(e)
    logging.error(msg)


DIV='-'*50
# ------------------------------------------------------------------------
# TensorRT 

def trt_init(model_conf, first_frame=None):
    """ 初始化 TensorRT Engine """
    logging.info('Init TensorRT Engine')

    try:
        trg = api.get(model_conf)
        runtime, palette = trg.load_model(model_conf)
        draw = trt_draw()
    except Exception as e:
        trg = e
        runtime, palette, draw = None, None, None

    return trg, runtime, draw, palette

def trt_inference(frame, uuid, model_conf, trg, runtime, draw, palette, ret_draw=True):
    """ 進行 AI 辨識 """
    ret, info = False, None
    
    try:
        info = trg.inference(runtime, frame, model_conf)
        if ret_draw:
            frame = draw.draw_detections(info, palette, model_conf)
        ret = True
        
        info.pop('frame', None)

    except Exception as e:
        ret = False
        logging.error(e)
        
    finally:
        if ret:
            # do something if inference success  ...
            for idx, det in enumerate(info['detections']):
                # clear the items of human pose 
                [ det.pop(key, None) for key in ['peaks', 'drawer', 'objects'] ]
                # convert bounding box from float to int
                for key in ['xmin', 'xmax', 'ymin', 'ymax']:
                    det[key] = int(float(det[key])) if det[key]!=None else det[key]
                # update detections
                info['detections'][idx] = det

        return ret, info, frame
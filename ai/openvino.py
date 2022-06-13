import sys, os, time, copy, logging
from flask import Blueprint, current_app
sys.path.append(os.getcwd())
try:
    from init_i.utils import Draw as vino_draw
except Exception as e:
    logging.error(e)
# ------------------------------------------------------------------------
# OpenVINO
""" 初始化 OpenVINO """
def vino_init(prim_conf, first_frame=None):
    logging.info('Init OpenVINO')
    try:
        if 'obj' in prim_conf['tag']:
            from init_i.obj import ObjectDetection as trg
        if "cls" in prim_conf['tag']:
            from init_i.cls import Classification as trg
        if "seg" in prim_conf['tag']:
            from init_i.seg import Segmentation as trg
        if "pose" in prim_conf['tag']:
            from init_i.pose import Pose as trg
        
        trg = trg()
        model, color_palette = trg.load_model(prim_conf, first_frame) if "pose" in prim_conf['tag'] else trg.load_model(prim_conf)
        draw = vino_draw()
        runtime, palette = model, color_palette
    
    except Exception as e:
        trg = e
        runtime, palette, draw = None, None, None

    return trg, runtime, draw, palette

""" 進行 AI 辨識 """
def vino_inference(frame, uuid, model_conf, trg, runtime, draw, palette, ret_draw=True):
    
    ret, info = False, None
    
    try:
        info = trg.inference(runtime, frame, model_conf)
            
        if info is not None:
                
                if ret_draw:
                    frame = draw.draw_detections(info, palette, model_conf)
                ret = True
                info.pop('frame', None) # original
                info.pop('output_transform', None)    
                
                if not ('detections' in info.keys()):
                    logging.error('unexcepted key {}, should be "detections" in openvino'.format(info.keys()))
                else:
                    logging.debug('parse the results')
                    
                    for idx, det in enumerate(info['detections']): 
                        if model_conf['tag'] in ['cls', 'obj']:
                            # convert bounding box from float to int
                            for key in ['xmin', 'xmax', 'ymin', 'ymax']:
                                det[key] = int(float(det[key])) if det[key]!=None else det[key]
                            info['detections'][idx]=det
                        else:
                            logging.debug('not classification and object detection')
    
    except Exception as e:
        ret = False
        logging.error(e)

    return ret, info, frame
   
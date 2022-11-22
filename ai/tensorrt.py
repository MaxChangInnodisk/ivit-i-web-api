import logging, sys, os
from ivit_i.common import api

def trt_init(model_conf, first_frame=None):
    logging.info('Init TensorRT Engine')
    try:
        trg = api.get(model_conf)
        trg.load_model(model_conf)
    except Exception as e:
        raise Exception('Could not load AI Model')
    return trg
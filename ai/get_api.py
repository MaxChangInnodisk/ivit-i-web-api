from flask import current_app
import logging

def get_api(af=None):
    """
    import the custom ai module for web api
    """
    init, do_inference = None, None
    trg_af = current_app.config['AF'] if af==None else af
    logging.info("Loading AI API ({}) ...".format(trg_af))
    if trg_af in ['tensorrt', 'TensorRT', 'trt']:
        try:
            from ivit_i.web.ai.tensorrt import trt_init 
            from ivit_i.web.ai.tensorrt import trt_inference 
            init = trt_init
            do_inference = trt_inference
        except Exception as e:
            raise Exception(e)

    elif trg_af in ['openvino', 'OpenVINO', 'vino']:
        try:
            from ivit_i.web.ai.openvino import vino_init
            from ivit_i.web.ai.openvino import vino_inference 
            init = vino_init
            do_inference = vino_inference
        except Exception as e:
            raise Exception(e)

    elif trg_af in ['vitis-ai', 'Vitis-ai', 'Vitis', 'vitis']:
        try:
            from ivit_i.web.ai.vitis import vitis_init
            from ivit_i.web.ai.vitis import vitis_inference 
            init = vitis_init
            do_inference = vitis_inference
        except Exception as e:
            raise Exception(e)
    
    if None in [init, do_inference]:
        msg = "Could not import framework API, please check the script in ivit_i.web.ai"
        logging.error(msg)
        raise Exception(msg)
    return init, do_inference
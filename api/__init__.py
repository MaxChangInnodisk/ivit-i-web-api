# import logging, os
# from flask import abort, current_app, request
# import cv2, time, logging, base64, threading, os, sys, copy, json

# from ..tools.common import handle_exception

# from werkzeug.utils import secure_filename

# # Define app config key
# AF              = "AF"
# TASK_LIST       = "TASK_LIST"
# DATA            = "DATA"
# TEMP_PATH       = "TEMP_PATH"
# PROC            = "proc"
# IMPORT_PROC     = "IMPORT_PROC"
# TRT             = "tensorrt" 

# # Define key for request data
# FRAMEWORK_KEY   = "framework"
# SOURCE_KEY      = "source"
# THRES_KEY       = "thres"

# # Define key for ZIP file from iVIT-T
# LABEL_NAME      = "classes"
# CLS             = "cls"
# OBJ             = "obj"
# DARKNET         = "darknet"
# CLASSIFICATION_KEY  = "classification"
# YOLO_KEY            = "yolo"

# # Define extension for ZIP file form iVIT-T
# DARK_LABEL_EXT  = CLS_LABEL_EXT = ".txt"        # txt is the category list
# DARK_JSON_EXT   = CLS_JSON_EXT  = ".json"       # json is for basic information like input_shape, preprocess

# ## Darknet format for tensorrt
# DARK_MODEL_EXT  = ".weights"    
# DARK_CFG_EXT    = ".cfg"

# ## onnx format for tensorrt
# CLS_MODEL_EXT   = ".onnx"

# ## ir model for openvino
# IR_MODEL_EXT    = ".xml"

# def get_request_file(save_file=False):
#     """
#     Get request file
#      - Argument
#         - save_file
#             - type: bool
#             - desc: set True if need to save file
#      - Output
#         - file name/path
#             - type: String
#             - desc: return file path if save_file is True, on the other hand, return name
#     """
    
#     file        = request.files[SOURCE_KEY]
#     file_name   = secure_filename(file.filename)
    
#     if save_file:
#         try:
#             file_path = os.path.join(current_app.config[DATA], secure_filename(file_name))
#             file.save( file_path )
#         except Exception as e:
#             err = handle_exception(e, "Error when saving file ...")
#             abort(404, {'message': err } )

#         return file_path
    
#     return file_name

# def get_request_data():
#     """ Get data form request and parse content. """
#     # Support form data and json
#     data = dict(request.form) if bool(request.form) else request.get_json()

#     # Put framework information into data
#     if FRAMEWORK_KEY not in data.keys(): 
#         data.update( { FRAMEWORK_KEY : current_app.config['AF'] } )

#     # Source: If got new source
#     if bool(request.files):
#         file_path = get_request_file(save_file=True)
#         data[SOURCE_KEY] = file_path
#         logging.debug("Get data ({})".format(data[SOURCE_KEY]))
        
#     # Set the format of thres to float
#     data[THRES_KEY]=float( data[THRES_KEY] )
    
#     # Print out to check information
#     print_data(data)

#     return data

# def print_title(title):
#     logging.info( "{}\n{}".format('-' * 3, title) )

# def print_data(data, title='Check request data'):
#     logging.debug(title)
#     [ logging.debug(" - {}: {}".format(key, data)) for key, val in data.items() ]


# def frame2btye(frame):
#     """
#     Convert the image with numpy array format to btye ( base64 )

#     - Arguments
#         - frame
#             - type: numpy.array
#     - Output
#         - ret
#             - type: dict
#             - parameters
#                 - image
#                     - type: btye
#                     - desc: the image which format is btye
#                 - height
#                     - type: int
#                     - desc: the orginal image height
#                 - width
#                     - type: int
#                     - desc: the orginal image width
#                 - channel
#                     - type: int
#                     - desc: the orginal image channel
#     """
#     ret, (h,w,c) = None, frame.shape
#     frame_base64 = base64.encodebytes(
#         cv2.imencode('.jpg', frame)[1].tobytes()
#     ).decode("utf-8")

#     ret = {
#         "image"     : frame_base64,
#         "height"    : h,
#         "width"     : w,
#         "channel"   : c
#     }
#     return ret

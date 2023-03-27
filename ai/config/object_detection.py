# Copyright (c) 2023 Innodisk Corporation
# 
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT


obj_yolo_pattern = {
    "tag": "obj",
    "framework": {
        "model_path": "./path/to/yolov3-model",
        "label_path": "./path/to/yolov3-label",
        "anchors": [        # 18
            10,
            13,
            16,
            30,
            33,
            23,
            30,
            61,
            62,
            45,
            59,
            119,
            116,
            90,
            156,
            198,
            373,
            326
        ],
        "architecture_type": "yolo",
        "device": "CPU",
        "thres": 0.6,
        "input_size": "3,416,416",
        "preprocess": "caffe"
    }
}

obj_yolov4_pattern = {
    "tag": "obj",
    "framework": {
        "model_path": "./path/to/yolov4-model",
        "label_path": "./path/to/yolov4-label",
        "anchors": [        # tiny is 12 , yolov4 is 18
            10,
            14,
            23,
            27,
            37,
            58,
            81,
            82,
            135,
            169,
            344,
            319
        ],
        "architecture_type": "yolov4",
        "device": "CPU",
        "thres": 0.6,
        "input_size": "3,416,416",
        "preprocess": "caffe"
    }
}
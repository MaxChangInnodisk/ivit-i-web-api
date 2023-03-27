# Copyright (c) 2023 Innodisk Corporation
# 
# This software is released under the MIT License.
# https://opensource.org/licenses/MIT

cls_pattern = {
    "tag": "cls",
    "framework": {
        "model_path": "path/to/model",
        "label_path": "path/to/label",
        "input_size": "3,224,224",
        "preprocess": "torch",
        "device": "CPU",
        "thres": 0.7
    }
}
import GPUtil, logging, os
import uuid, sys, traceback
import subprocess
import socket

def get_gpu_info():
    gpus = GPUtil.getGPUs()
    ret = dict()
    for gpu in gpus:
        ret.update({ gpu.name: {
                
                "id": gpu.id,
                "name": gpu.name, 
                "uuid": gpu.uuid, 
                "load": round(gpu.load*100, 3), 
                "memoryUtil": round(gpu.memoryUtil*100, 3), 
                "temperature": gpu.temperature
        }})
    return ret

def get_address():
    st = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:       
        st.connect(('10.255.255.255', 1))
        IP = st.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        st.close()
    return IP

def gen_uuid(name:str, len:int=8) -> str:
    """
    Generate uuid for each application
    """
    return str(uuid.uuid4())[:len]

def get_v4l2() -> list:
    ret = subprocess.run("ls /dev/video*", shell=True, stdout=subprocess.PIPE, encoding='utf8').stdout
    ret_list = ret.strip().split('\n')
    return ret_list

def handle_exception(error, title="Error", exit=False):
    e = error
    error_class = e.__class__.__name__ #取得錯誤類型
    detail = e.args[0] #取得詳細內容
    cl, exc, tb = sys.exc_info() #取得Call Stack
    lastCallStack = traceback.extract_tb(tb)[-1] #取得Call Stack的最後一筆資料
    fileName = lastCallStack[0] #取得發生的檔案名稱
    lineNum = lastCallStack[1] #取得發生的行號
    funcName = lastCallStack[2] #取得發生的函數名稱
    errMsg = "File \"{}\", line {}, in {}: [{}] {}".format(fileName, lineNum, funcName, error_class, detail)
    logging.error("{}\n{}".format(title, errMsg))

    if exit:
        sys.exit()
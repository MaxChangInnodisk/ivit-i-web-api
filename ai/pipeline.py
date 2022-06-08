import cv2, time, logging, os, sys

def check_file_exist(path):
    return True if os.path.exists(path) else False
        
class Img:
    def __init__(self, input_data) -> None:
        self.img = cv2.imread(input_data)

    def release(self):
        self.img=None

    def __del__(self):
        self.img=None

    def read(self):
        # if not None then return true
        return (self.img is not None), self.img

class Source():
    
    def __init__(self, input_data, intype):

        self.src = None
        self.input_data = input_data.rstrip().replace('\n', '').replace(' ', '')
        self.intype = intype
        self.status, self.err = self.check_status()
        logging.warning('Detect source type is : {}'.format(self.intype))
        if self.status:
            if intype in ['V4L2', 'Video']:
                self.src = cv2.VideoCapture(self.input_data)
            elif intype=='Image':
                self.src = Img(self.input_data)            
            elif intype=='RTSP':
                self.src = cv2.VideoCapture(self.input_data)
            else:
                logging.error('Unexcepted input data.')

        self.start_time = time.time() 
        self.stop_time  = self.start_time + 5
        self.isStop = False
        
    def __del__(self):
        self.stop()

    def check_status(self):
        status, err_msg = True, ""
        if self.intype in ['video', 'image', 'V4L2']:
            # check file exist
            if not os.path.exists(self.input_data):
                status = False
                err_msg = "Could not find data ({})".format(self.input_data)
        
        return status, err_msg

    def get_status(self):            
        return self.status, self.err

    def get_type(self):
        return self.intype

    def stop(self):
        self.isStop = True
    
    def release(self):
        try:
            self.isStop = True
            self.src.release()
        except:
            logging.warning('Could not release object')
        finally:
            logging.warning('Set source to `None`')
            self.src=None
    
    def get_frame(self):
        return self.src.read()

if __name__ == "__main__":
    logging.info('Testing source.py')

    # rtsp -> rtsp://admin:admin@172.16.21.1:554/snl/live/1/1/n
    rtsp_path = "rtsp://admin:admin@172.16.21.1:554/snl/live/1/1/n"
    src = Source(rtsp_path, "rtsp")
    
    while(True):
        ret, frame = src.get_frame()
        cv2.imshow('Test', frame)
        if cv2.waitKey(1)==ord('q'):
            break
    
    src.release()
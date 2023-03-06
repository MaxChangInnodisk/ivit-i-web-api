import requests, json, logging, os, sys

# NOTE: before v1.1, we have to 
sys.path.append(os.getcwd())
from ivit_i.utils.err_handler import handle_exception

HEAD_MAP = {
    "json": {'Content-type': 'application/json'}
}

KEY_RESP_DATA = "data"
KEY_RESP_CODE = "status_code"

def response_status(code):
    """ Return the response is success or not """
    return (str(code)[0] not in [ '4', '5' ])

def request_exception(exception, calling_api):
    """ Handle exception from sending request """

    RESP_EXCEPTION_MAP = {
        Exception: {
            KEY_RESP_DATA: f"Unxepected Error !!! ({handle_exception(exception)})",
            KEY_RESP_CODE: 400        
        },
        requests.Timeout: { 
            KEY_RESP_DATA: f"Request Time Out !!! ({calling_api})",
            KEY_RESP_CODE: 400 
        },
        requests.ConnectionError: { 
            KEY_RESP_DATA: f"Connect Error !!! ({calling_api})",
            KEY_RESP_CODE: 400 
        }
    }

    return ( False, RESP_EXCEPTION_MAP.get(type(exception)) )
    
def resp_to_json(resp):
    """ Parsing response and combine to JSON format """

    code = resp.status_code
    data = { KEY_RESP_CODE: code }

    # Parse from string
    try: 
        resp_data = json.loads(resp.text)
    except Exception as e: 
        resp_data = resp.text

    if type(resp_data) == str:
        logging.debug('Convert string response to json with key `data`')
        resp_data = { KEY_RESP_DATA: resp_data }
    
    # Merge data  
    data.update(resp_data)
    return response_status(code), data

def send_post_api(trg_url, data, h_type='json', timeout=10, stderr=True):
    """ Using request to simulate POST method """
    
    try:
        resp = requests.post(trg_url, data=json.dumps(data), headers=HEAD_MAP[h_type], timeout=timeout)
        return resp_to_json(resp)

    except Exception as e:
        return request_exception(exception=e, calling_api=trg_url) 

def send_get_api(trg_url, h_type='json', timeout=10):
    """ Using request to simulate GET method """

    try:
        resp = requests.get(trg_url, headers=HEAD_MAP[h_type], timeout=10)
        return resp_to_json(resp)
    
    except Exception as e:
        return request_exception(exception=e, calling_api=trg_url) 

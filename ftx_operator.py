#import time
#import numpy as np
#from datetime import datetime, timedelta
#import sheets_service
from google.cloud import secretmanager_v1beta1 as secretmanager
import ftx

project_id = 'trading-bot-299323'
api_key_name = 'ftx-api-key'
api_secret_name = 'ftx-api-secret'
version = 1

client = secretmanager.SecretManagerServiceClient()
secret_path_1 = client.secret_version_path(project_id, api_key_name, version)
secret_path_2 = client.secret_version_path(project_id, api_secret_name, version)
API_KEY = client.access_secret_version(request={"name": secret_path_1}).payload.data.decode('UTF-8')
API_SECRET = client.access_secret_version(request={"name": secret_path_2}).payload.data.decode('UTF-8')

client = ftx.FtxClient(api_key=API_KEY, api_secret=API_SECRET)

def buy_sl_orders_ftx():
    return
    #client.get_open_orders('BTC/USD')
    #client.place_order('BTC/USD', 'sell', 12345.0, 10)
    #client.modify_order(9596912, 50000.0, 1).result()
    #client.cancel_order(9596912).result()


def place_tp_orders_ftx():
    return

import time
from flask import Flask, Response
from deGiro_operator import attempt_trade_deGiro
from threading import Thread

app = Flask(__name__)
run_auto_trade = False
message = ''


@app.route('/')
def hello():
    return 'Hello to the Auto-Trading Stocks application!'


@app.route('/start')
def start_auto_trade():
    global run_auto_trade
    run_auto_trade = True
    return Response(run_process(), mimetype="text/html")


@app.route('/stop')
def stop_auto_trade():
    global run_auto_trade
    run_auto_trade = False
    return "Application stopped"


def record_loop():
    global run_auto_trade, message
    while run_auto_trade:
        message = attempt_trade_deGiro()
        print(message)
        time.sleep(60*5)


def run_process():
    t = Thread(target=record_loop)
    t.start()
    return 'Processing... :' + message


if __name__ == '__main__':
    '''
    app.run(host='127.0.0.1', port=8080, debug=True, use_reloader=False)
    p = Process(target=record_loop)
    p.start()
    p.join()
    '''

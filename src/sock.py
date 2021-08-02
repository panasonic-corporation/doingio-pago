import os
import threading
from flask import Flask
from flask_socketio import SocketIO

PORT = 7000
HOST = '0.0.0.0'
DATA_PATH = '/boot/VIEWER/data/'

app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins='*')


def start_sock_thread():
    # start socketio
    th = threading.Thread(target=start_sock)
    th.start()


@socketio.on('connect')
def on_connect():
    files = os.listdir(DATA_PATH)
    socketio.emit('connected', files)


def start_sock():
    socketio.run(app, port=PORT, host=HOST)


def emit_message(message):
    socketio.emit('message', message)

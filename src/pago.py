import argparse
import io
import os
import sys
import time
import json
import logging
import numpy as np
import picamera.array
import picamera
import RPi.GPIO as GPIO
import datetime
import pygame
import edgetpu.classification.engine
import pixels
import sock

PIN1 = 32
PIN2 = 33
WIDTH = 400
HEIGHT = 400
INFERENCE_WIDTH = 224
INFERENCE_HEIGHT = 224
FRAMERATE = 30
ROTATION = 0

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANT_LABEL_PATH = os.path.join(BASE_DIR, 'json/plant.json')
INSECT_LABEL_PATH = os.path.join(BASE_DIR, 'json/insect.json')
PLANT_MODEL_PATH = \
    os.path.join(BASE_DIR,
                 'models/',
                 'mobilenet_v2_1.0_224_inat_plant_quant_edgetpu.tflite')
INSECT_MODEL_PATH = \
    os.path.join(BASE_DIR,
                 'models',
                 'mobilenet_v2_1.0_224_inat_insect_quant_edgetpu.tflite')
TRY_AGAIN_VOICE_PATH = \
    os.path.join(BASE_DIR,
                 'voices',
                 'Ooops,_please_try_again.mp3')
READY_VOICE_PATH = os.path.join(BASE_DIR, 'voices/ready.mp3')

pix = pixels.Pixels()
sock.start_sock_thread()

# setup pygame.mixer
pygame.mixer.init(frequency=24000)
music = pygame.mixer.music


def speak(path):
    if music.get_busy():
        music.stop()
    else:
        if os.path.exists(path):
            music.unload()
            music.load(path)
            music.play()
        else:
            logging.warning(path + ' file does not exist.')


def save_image(camera, results, labels):
    # make path
    date = datetime.datetime.now().date().strftime('%Y-%m-%d')
    time = datetime.datetime.now().time().strftime('%H%M%S')
    datestr = '{}_{}'.format(date, time)
    path = os.path.join(sock.DATA_PATH, datestr)
    os.makedirs(path)

    # capture
    camera.capture(os.path.join(path, 'image.jpg'))

    # make meta data
    candidates = [{
        'label': labels[item[0]]['name'],
        'score': int(item[1] * 1000)/10  # unit = %
    } for item in results]
    logging.info('===RESULT===')
    for item in candidates:
        logging.info('%s %.1f' % (item['label'], item['score']))
    meta = {
      'dateTime': datestr,
      'date': date,
      'time': time,
      'top_label': labels[results[0][0]]['name'].upper(),
      'top_score': int(results[0][1] * 1000) / 10,  # unit = %
      'kg': labels[results[0][0]]['kg'],
      'candidates': candidates
    }

    # save meta data
    with open(os.path.join(path, 'meta.json'), mode='w') as f:
        f.write(json.dumps(meta))

    # emit message
    sock.emit_message(datestr)


def main():
    def on_push_up(gpio_pin):
        if gpio_pin == PIN2 and GPIO.input(PIN2):
            if len(filtered_results) > 0:
                if labels[filtered_results[0][0]]['kg'] == '':
                    speak(labels[filtered_results[0][0]]['label_voice'])
                else:
                    speak(labels[filtered_results[0][0]]['kg_voice'])
            else:
                speak(TRY_AGAIN_VOICE_PATH)

    # logging settings
    logging.basicConfig(level=logging.INFO)

    # parse argument
    parser = argparse.ArgumentParser()
    parser.add_argument('--category',
                        help='Category you want to detect.',
                        required=True)
    args = parser.parse_args()

    # set label/model path
    category = args.category
    if category == 'plant':
        label_path = PLANT_LABEL_PATH
        model_path = PLANT_MODEL_PATH
    elif category == 'insect':
        label_path = INSECT_LABEL_PATH
        model_path = INSECT_MODEL_PATH
    else:
        logging.error('Specify insect or plant for the category.')
        sys.exit(1)

    # GPIO settings
    GPIO.setmode(GPIO.BOARD)
    GPIO.setup(PIN1, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(PIN2, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.add_event_detect(PIN2, GPIO.RISING, on_push_up, bouncetime=300)

    # read json file
    with open(label_path, 'r', encoding='utf-8') as f:
        labels = [{
            'name': l['name'],
            'kg': l['kg'],
            'label_voice': os.path.join(BASE_DIR,
                                        'voices',
                                        category,
                                        'label',
                                        l['voice']),
            'kg_voice': os.path.join(BASE_DIR,
                                     'voices',
                                     category,
                                     'kg',
                                     l['voice'])
        } for l in json.load(f)]

    # load model
    engine = edgetpu.classification.engine.ClassificationEngine(model_path)

    with picamera.PiCamera() as camera:
        # camera settings
        camera.resolution = (WIDTH, HEIGHT)
        camera.framerate = FRAMERATE
        camera.rotation = ROTATION
        _, width, height, channels = engine.get_input_tensor_shape()
        camera.start_preview()
        # speak ready
        speak(READY_VOICE_PATH)
        try:
            input_img = np.zeros(INFERENCE_WIDTH * INFERENCE_HEIGHT * 3, dtype=np.uint8)
            while True:
                if GPIO.input(PIN1) == 0:  # while hold down
                    if music.get_busy():
                        music.stop()
                    for _ in camera.capture_continuous(input_img,
                                                       format='rgb',
                                                       resize=(INFERENCE_WIDTH,
                                                               INFERENCE_HEIGHT),
                                                       use_video_port=True):
                        start_ms = time.time()
                        results = engine.ClassifyWithInputTensor(input_img,
                                                                 top_k=10)
                        elapsed_ms = time.time() - start_ms
                        # ignore "background" label
                        filtered_results = [r for r in results if r[0] != len(labels) - 1]
                        if len(filtered_results) > 0:
                            logging.info('%s %.1f\n%.2fms' %
                                         (labels[filtered_results[0][0]]['name'],
                                          int(filtered_results[0][1] * 1000) / 10,  # unit = %
                                          elapsed_ms * 1000.0))
                            pix.flash(int(filtered_results[0][1] * 100))
                        else:
                            logging.info('no result')
                            if pix.brightness != 0:
                                pix.flash(0)
                        if GPIO.input(PIN1) == 1:
                            if len(filtered_results) > 0:
                                # play sound
                                speak(labels[filtered_results[0][0]]['label_voice'])
                                # save image
                                save_image(camera, filtered_results, labels)
                            else:
                                speak(TRY_AGAIN_VOICE_PATH)
                            pix.flash(0)
                            break
        finally:
            logging.info('\nbreak')
            pix.clear()
            GPIO.remove_event_detect(PIN2)
            GPIO.cleanup()
            camera.stop_preview()


if __name__ == '__main__':
    main()

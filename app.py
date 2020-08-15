# import the necessary packages
# flask
import os
from flask import Flask, request, redirect, url_for, render_template, flash
from werkzeug.utils import secure_filename

# cat detector
from pyimagesearch.nms import non_max_suppression
from pyimagesearch import config
from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
from tensorflow.keras.preprocessing.image import img_to_array
from tensorflow.keras.models import load_model

import numpy as np
import argparse
import imutils
import pickle
import cv2

app = Flask(__name__, static_url_path="/static")
UPLOAD_FOLDER = 'static/uploads/'
DOWNLOAD_FOLDER = 'static/downloads/'
ALLOWED_EXTENSIONS = {'jpg', 'png', '.jpeg'}

# APP CONFIGURATIONS
app.config['SECRET_KEY'] = 'YourSecretKey'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['DOWNLOAD_FOLDER'] = DOWNLOAD_FOLDER
# limit upload size to 2mb
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024 

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file attached in request')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No file selected')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(UPLOAD_FOLDER, filename))
            process_file(os.path.join(UPLOAD_FOLDER, filename), filename)
            data={
                "processed_img": 'static/downloads/' + filename,
                "uploaded_img": 'static/uploads/' + filename
            }
        return render_template("index.html", data=data)
    return render_template('index.html')

def process_file(path, filename):
    detect_object(path, filename)

def detect_object(path, filename):
    # load the our fine-tuned model and label binarizer from disk
    model = load_model('model/cat_detector.h5')
    lb = pickle.loads(open('model/label_encoder.pickle', "rb").read())

    # load the input image from disk
    image = cv2.imread(path)
    image = imutils.resize(image, width=500)

    # run selective search on the image to generate bounding box proposal
    # regions=
    ss = cv2.ximgproc.segmentation.createSelectiveSearchSegmentation()
    ss.setBaseImage(image)
    ss.switchToSelectiveSearchFast()
    rects = ss.process()

    # initialize the list of region proposals that we'll be classifying
    # along with their associated bounding boxes
    proposals = []
    boxes = []

    # loop over the region proposal bounding box coordinates generated by
    # running selective search
    for (x, y, w, h) in rects[:config.MAX_PROPOSALS_INFER]:
        # extract the region from the input image, convert it from BGR to
        # RGB channel ordering, and then resize it to the required input
        # dimensions of our trained CNN
        roi = image[y:y + h, x:x + w]
        roi = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
        roi = cv2.resize(roi, config.INPUT_DIMS,
            interpolation=cv2.INTER_CUBIC)

        # further preprocess by the ROI
        roi = img_to_array(roi)
        roi = preprocess_input(roi)

        # update our proposals and bounding boxes lists
        proposals.append(roi)
        boxes.append((x, y, x + w, y + h))

    # convert the proposals and bounding boxes into NumPy arrays
    proposals = np.array(proposals, dtype="float32")
    boxes = np.array(boxes, dtype="int32")

    # classify each of the proposal ROIs using fine-tuned model
    proba = model.predict(proposals)

    # find the index of all predictions that are positive for the
    # "cat" class
    labels = lb.classes_[np.argmax(proba, axis=1)]
    idxs = np.where(labels == 'cat')[0]

    # use the indexes to extract all bounding boxes and associated class
    # label probabilities associated with the "cat" class
    boxes = boxes[idxs]
    proba = proba[idxs][:, 0]

    # further filter indexes by enforcing a minimum prediction
    # probability be met
    idxs = np.where(proba >= config.MIN_PROBA)
    boxes = boxes[idxs]
    proba = proba[idxs]

    # clone the original image so that we can draw on it
    clone = image.copy()

    # loop over the bounding boxes and associated probabilities
    for (box, prob) in zip(boxes, proba):
        # draw the bounding box, label, and probability on the image
        (startX, startY, endX, endY) = box
        cv2.rectangle(clone, (startX, startY), (endX, endY),
            (0, 255, 0), 2)
        y = startY - 10 if startY - 10 > 10 else startY + 10
        text= "Cat: {:.2f}%".format(prob * 100)
        cv2.putText(clone, text, (startX, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)

    # run non-maxima suppression on the bounding boxes
    boxIdxs = non_max_suppression(boxes, proba)

    # loop over the bounding box indexes
    for i in boxIdxs:
        # draw the bounding box, label, and probability on the image
        (startX, startY, endX, endY) = boxes[i]
        cv2.rectangle(image, (startX, startY), (endX, endY),
            (0, 255, 0), 2)
        y = startY - 10 if startY - 10 > 10 else startY + 10
        text= "Cat: {:.2f}%".format(proba[i] * 100)
        cv2.putText(image, text, (startX, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 2)

    # show the output image *after* running NMS
    cv2.imwrite(f"{DOWNLOAD_FOLDER}{filename}", image)
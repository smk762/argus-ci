import importlib

import nudenet
from nudenet import NudeDetector
from ultralytics import YOLO
import ultralytics.engine


def lazy():
    from nudenet.detector import NudeDetector as D
    return D, importlib.import_module("ultralytics"), __import__("nudenet")

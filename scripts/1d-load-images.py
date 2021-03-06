#!/usr/bin/python

import sys
sys.path.insert(0, "/usr/local/lib/python2.7/site-packages/")

import argparse
import commands
import cv2
import fnmatch
import os.path

sys.path.append('../lib')
import ProjectMgr

# for all the images in the project image_dir, load the image meta data

# this script produces nothing other than loading some data and quitting.

parser = argparse.ArgumentParser(description='Load the project\'s images.')
parser.add_argument('--project', required=True, help='project directory')
parser.add_argument('--recompute-sizes', action='store_true', help='recompute image sizes')

args = parser.parse_args()

proj = ProjectMgr.ProjectMgr(args.project)
proj.load_image_info(force_compute_sizes=args.recompute_sizes)

#!/usr/bin/python

# find our custom built opencv first
import sys
sys.path.insert(0, "/usr/local/lib/python2.7/site-packages/")

import argparse
import cv2
import math
import fractions
from matplotlib import pyplot as plt 
import numpy as np
import os
import pyexiv2
import re
#from scipy.interpolate import InterpolatedUnivariateSpline
from scipy import interpolate # strait up linear interpolation, nothing fancy

parser = argparse.ArgumentParser(description='correlate movie data to flight data.')
parser.add_argument('--movie', required=False, help='original movie if extracting frames')
parser.add_argument('--hud', required=False, help='original movie if drawing hud')
parser.add_argument('--scale', type=float, default=1.0, help='scale input')
parser.add_argument('--movie-log', required=True, help='movie log file')
parser.add_argument('--resample-hz', type=float, default=30.0, help='resample rate (hz)')
parser.add_argument('--apm-log', help='APM tlog converted to csv')
parser.add_argument('--aura-dir', help='Aura flight log directory')
parser.add_argument('--stop-count', type=int, default=1, help='how many non-frames to absorb before we decide the movie is over')
args = parser.parse_args()

r2d = 180.0 / math.pi
counter = 0
stop_count = 0

class Fraction(fractions.Fraction):
    """Only create Fractions from floats.

    >>> Fraction(0.3)
    Fraction(3, 10)
    >>> Fraction(1.1)
    Fraction(11, 10)
    """

    def __new__(cls, value, ignore=None):
        """Should be compatible with Python 2.6, though untested."""
        return fractions.Fraction.from_float(value).limit_denominator(99999)

def dms_to_decimal(degrees, minutes, seconds, sign=' '):
    """Convert degrees, minutes, seconds into decimal degrees.

    >>> dms_to_decimal(10, 10, 10)
    10.169444444444444
    >>> dms_to_decimal(8, 9, 10, 'S')
    -8.152777777777779
    """
    return (-1 if sign[0] in 'SWsw' else 1) * (
        float(degrees)        +
        float(minutes) / 60   +
        float(seconds) / 3600
    )


def decimal_to_dms(decimal):
    """Convert decimal degrees into degrees, minutes, seconds.

    >>> decimal_to_dms(50.445891)
    [Fraction(50, 1), Fraction(26, 1), Fraction(113019, 2500)]
    >>> decimal_to_dms(-125.976893)
    [Fraction(125, 1), Fraction(58, 1), Fraction(92037, 2500)]
    """
    remainder, degrees = math.modf(abs(decimal))
    remainder, minutes = math.modf(remainder * 60)
    return [Fraction(n) for n in (degrees, minutes, remainder * 60)]

if args.resample_hz <= 0.001:
    print "Resample rate (hz) needs to be greater than zero."
    quit()
    
# load movie log
movie = []
with open(args.movie_log, 'rb') as f:
    for line in f:
        movie.append( re.split('[,\s]+', line.rstrip()) )

flight_imu = []
flight_gps = []
flight_air = []
last_imu_time = -1
last_gps_time = -1
last_air_time = -1

if args.apm_log:
    # load APM flight log
    agl = 0.0
    with open(args.apm_log, 'rb') as f:
        for line in f:
            tokens = re.split('[,\s]+', line.rstrip())
            if tokens[7] == 'mavlink_attitude_t':
                timestamp = float(tokens[9])/1000.0
                print timestamp
                if timestamp > last_imu_time:
                    flight_imu.append( [timestamp,
                                        float(tokens[17]), float(tokens[19]),
                                        float(tokens[21]),
                                        float(tokens[11]), float(tokens[13]),
                                        float(tokens[15])] )
                    last_imu_time = timestamp
                else:
                    print "ERROR: IMU time went backwards:", timestamp, last_imu_time
            elif tokens[7] == 'mavlink_gps_raw_int_t':
                timestamp = float(tokens[9])/1000000.0
                if timestamp > last_gps_time - 1.0:
                    flight_gps.append( [timestamp,
                                        float(tokens[11]) / 10000000.0,
                                        float(tokens[13]) / 10000000.0,
                                        float(tokens[15]) / 1000.0,
                                        agl] )
                    last_gps_time = timestamp
                else:
                    print "ERROR: GPS time went backwards:", timestamp, last_gps_time
            elif tokens[7] == 'mavlink_terrain_report_t':
                agl = float(tokens[15])
elif args.aura_dir:
    # load Aura flight log
    imu_file = args.aura_dir + "/imu-0.txt"
    gps_file = args.aura_dir + "/gps-0.txt"
    air_file = args.aura_dir + "/air-0.txt"
    
    last_time = 0.0
    with open(imu_file, 'rb') as f:
        for line in f:
            tokens = re.split('[,\s]+', line.rstrip())
            timestamp = float(tokens[0])
            if timestamp > last_time:
                flight_imu.append( [tokens[0], tokens[1], tokens[2],
                                    tokens[3], 0.0, 0.0, 0.0] )
            else:
                print "ERROR: time went backwards:", timestamp, last_time
            last_time = timestamp

    last_time = 0.0
    with open(gps_file, 'rb') as f:
        for line in f:
            #print line
            tokens = re.split('[,\s]+', line.rstrip())
            timestamp = float(tokens[0])
            #print timestamp, last_time
            if timestamp > last_time:
                flight_gps.append( [tokens[0], tokens[1], tokens[2],
                                    tokens[3], 0.0] )
            else:
                print "ERROR: time went backwards:", timestamp, last_time
            last_time = timestamp

    last_time = 0.0
    with open(air_file, 'rb') as f:
        for line in f:
            #print line
            tokens = re.split('[,\s]+', line.rstrip())
            timestamp = float(tokens[0])
            #print timestamp, last_time
            if timestamp > last_time:
                flight_air.append( [tokens[0], tokens[1], tokens[2],
                                    tokens[3]] )
            else:
                print "ERROR: time went backwards:", timestamp, last_time
            last_time = timestamp
else:
    print "No flight log specified, cannot continue."
    quit()
    
# resample movie data
movie = np.array(movie, dtype=float)
movie_interp = []
x = movie[:,0]
movie_spl_roll = interpolate.interp1d(x, movie[:,2], bounds_error=False, fill_value=0.0)
movie_spl_pitch = interpolate.interp1d(x, movie[:,3], bounds_error=False, fill_value=0.0)
movie_spl_yaw = interpolate.interp1d(x, movie[:,4], bounds_error=False, fill_value=0.0)
xmin = x.min()
xmax = x.max()
print "movie range = %.3f - %.3f (%.3f)" % (xmin, xmax, xmax-xmin)
time = xmax - xmin
for x in np.linspace(xmin, xmax, time*args.resample_hz):
    movie_interp.append( [x, movie_spl_roll(x)] )
print "movie len:", len(movie_interp)

# resample flight data
flight_imu = np.array(flight_imu, dtype=float)
flight_interp = []
x = flight_imu[:,0]
flight_imu_p = interpolate.interp1d(x, flight_imu[:,1], bounds_error=False, fill_value=0.0)
flight_imu_q = interpolate.interp1d(x, flight_imu[:,2], bounds_error=False, fill_value=0.0)
flight_imu_r = interpolate.interp1d(x, flight_imu[:,3], bounds_error=False, fill_value=0.0)
flight_imu_roll = interpolate.interp1d(x, flight_imu[:,4], bounds_error=False, fill_value=0.0)
flight_imu_pitch = interpolate.interp1d(x, flight_imu[:,5], bounds_error=False, fill_value=0.0)
flight_imu_yaw = interpolate.interp1d(x, flight_imu[:,6], bounds_error=False, fill_value=0.0)
if args.apm_log:
    y_spline = flight_imu_r
elif args.aura_dir:
    y_spline = flight_imu_p
xmin = x.min()
xmax = x.max()
print "flight range = %.3f - %.3f (%.3f)" % (xmin, xmax, xmax-xmin)
time = xmax - xmin
for x in np.linspace(xmin, xmax, time*args.resample_hz):
    flight_interp.append( [x, y_spline(x)] )
print "flight len:", len(flight_interp)

flight_gps = np.array(flight_gps, dtype=np.float64)
x = flight_gps[:,0]
flight_gps_lat = interpolate.interp1d(x, flight_gps[:,1], bounds_error=False, fill_value=0.0)
flight_gps_lon = interpolate.interp1d(x, flight_gps[:,2], bounds_error=False, fill_value=0.0)
flight_gps_alt = interpolate.interp1d(x, flight_gps[:,3], bounds_error=False, fill_value=0.0)
flight_gps_agl = interpolate.interp1d(x, flight_gps[:,4], bounds_error=False, fill_value=0.0)

flight_air = np.array(flight_air, dtype=np.float64)
x = flight_air[:,0]
flight_air_speed = interpolate.interp1d(x, flight_air[:,3], bounds_error=False, fill_value=0.0)

# compute best correlation between movie and flight data logs
movie_interp = np.array(movie_interp, dtype=float)
flight_interp = np.array(flight_interp, dtype=float)
ycorr = np.correlate(movie_interp[:,1], flight_interp[:,1], mode='full')

# display some stats/info
max_index = np.argmax(ycorr)
print "max index:", max_index
shift = np.argmax(ycorr) - len(flight_interp)
print "shift (pos):", shift
start_diff = flight_interp[0][0] - movie_interp[0][0]
print "start time diff:", start_diff
time_shift = start_diff - (shift/args.resample_hz)
print "movie time shift:", time_shift

# estimate  tx, ty vs. r, q multiplier
tmin = np.amax( [np.amin(movie_interp[:,0]) + time_shift,
                np.amin(flight_interp[:,0]) ] )
tmax = np.amin( [np.amax(movie_interp[:,0]) + time_shift,
                np.amax(flight_interp[:,0]) ] )
print "overlap range (flight sec):", tmin, " - ", tmax

mqsum = 0.0
fqsum = 0.0
mrsum = 0.0
frsum = 0.0
count = 0
qratio = 1.0
for x in np.linspace(tmin, tmax, time*args.resample_hz):
    mqsum += abs(movie_spl_pitch(x-time_shift))
    mrsum += abs(movie_spl_yaw(x-time_shift))
    fqsum += abs(flight_imu_q(x))
    frsum += abs(flight_imu_r(x))
if fqsum > 0.001:
    qratio = mqsum / fqsum
if mrsum > 0.001:
    rratio = -mrsum / frsum
print "pitch ratio:", qratio
print "yaw ratio:", rratio

if args.movie:
    # extract frames
    print "Opening ", args.movie
    try:
        capture = cv2.VideoCapture(args.movie)
    except:
        print "error opening video"

    capture.read()
    counter += 1
    print "ok reading first frame"

    fps = capture.get(cv2.cv.CV_CAP_PROP_FPS)
    print "fps = %.2f" % fps
    fourcc = int(capture.get(cv2.cv.CV_CAP_PROP_FOURCC))
    w = capture.get(cv2.cv.CV_CAP_PROP_FRAME_WIDTH)
    h = capture.get(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT)

    last_time = 0.0
    abspath = os.path.abspath(args.movie)
    basename, ext = os.path.splitext(abspath)
    dirname = os.path.dirname(abspath)
    meta = dirname + "/image-metadata.txt"
    print "writing meta data to", meta
    f = open(meta, 'wb')
    while True:
        ret, frame = capture.read()
        if not ret:
            # no frame
            stop_count += 1
            print "no more frames:", stop_count
            if stop_count > args.stop_count:
                break
        else:
            stop_count = 0
            
        if frame == None:
            print "Skipping bad frame ..."
            continue
        time = float(counter) / fps + time_shift
        print "frame: ", counter, time
        counter += 1
        if time < tmin or time > tmax:
            continue
        if flight_gps_agl(time) < 20.0:
            continue
        yaw_deg = flight_imu_yaw(time)*r2d
        while yaw_deg < 0:
            yaw_deg += 360
        while yaw_deg > 360:
            yaw_deg -= 360
        # reject poses that are too far off N/S headings (temp hack)
        #if yaw_deg > 10 and yaw_deg < 170:
        #    continue
        #if yaw_deg > 190 and yaw_deg < 350:
        #    continue
        if time > last_time + 1.0:
            last_time = time
            file = basename + "-%06d" % counter + ".jpg"
            cv2.imwrite(file, frame)
            # geotag the image
            exif = pyexiv2.ImageMetadata(file)
            exif.read()
            lat_deg = float(flight_gps_lat(time))
            lon_deg = float(flight_gps_lon(time))
            altitude = float(flight_gps_alt(time))
            print lat_deg, lon_deg, altitude
            GPS = 'Exif.GPSInfo.GPS'
            exif[GPS + 'AltitudeRef']  = '0' if altitude >= 0 else '1'
            exif[GPS + 'Altitude']     = Fraction(altitude)
            exif[GPS + 'Latitude']     = decimal_to_dms(lat_deg)
            exif[GPS + 'LatitudeRef']  = 'N' if lat_deg >= 0 else 'S'
            exif[GPS + 'Longitude']    = decimal_to_dms(lon_deg)
            exif[GPS + 'LongitudeRef'] = 'E' if lon_deg >= 0 else 'W'
            exif[GPS + 'MapDatum']     = 'WGS-84'
            exif.write()
            head, tail = os.path.split(file)
            f.write("%s,%.8f,%.8f,%.4f,%.4f,%.4f,%.4f\n" % (tail, flight_gps_lat(time), flight_gps_lon(time), flight_gps_alt(time), flight_imu_yaw(time)*r2d, 0.0, 0.0))
    f.close()
    
if args.hud:
    K_RunCamHD2_1920x1080 \
        = np.array( [[ 971.96149426,   0.        , 957.46750602],
                     [   0.        , 971.67133264, 516.50578382],
                     [   0.        ,   0.        ,   1.        ]] )
    dist_runcamhd2_1920x1080 = [-0.26910665, 0.10580125, 0.00048417, 0.00000925, -0.02321387]
    K = K_RunCamHD2_1920x1080 * args.scale
    K[2,2] = 1.0
    dist = dist_runcamhd2_1920x1080

    font = cv2.FONT_HERSHEY_SIMPLEX
    # overlay hud
    print "Opening ", args.hud
    try:
        capture = cv2.VideoCapture(args.hud)
    except:
        print "error opening video"

    capture.read()
    counter += 1
    print "ok reading first frame"

    fps = capture.get(cv2.cv.CV_CAP_PROP_FPS)
    print "fps = %.2f" % fps
    fourcc = int(capture.get(cv2.cv.CV_CAP_PROP_FOURCC))
    w = capture.get(cv2.cv.CV_CAP_PROP_FRAME_WIDTH)
    h = capture.get(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT)

    last_time = 0.0

    while True:
        ret, frame = capture.read()
        if not ret:
            # no frame
            stop_count += 1
            print "no more frames:", stop_count
            if stop_count > args.stop_count:
                break
        else:
            stop_count = 0
            
        if frame == None:
            print "Skipping bad frame ..."
            continue
        time = float(counter) / fps + time_shift
        print "frame: ", counter, time
        counter += 1
        yaw_deg = flight_imu_yaw(time)*r2d
        while yaw_deg < 0:
            yaw_deg += 360
        while yaw_deg > 360:
            yaw_deg -= 360
        lat_deg = float(flight_gps_lat(time))
        lon_deg = float(flight_gps_lon(time))
        altitude = float(flight_gps_alt(time))
        speed = float(flight_air_speed(time))
        
        method = cv2.INTER_AREA
        #method = cv2.INTER_LANCZOS4
        frame_scale = cv2.resize(frame, (0,0), fx=args.scale, fy=args.scale,
                                 interpolation=method)
        frame_undist = cv2.undistort(frame_scale, K, np.array(dist))

        cv2.putText(frame_undist, 'alt = %.0f' % altitude, (100, 100), font, 1.5, (0,255,0), 2,cv2.CV_AA)
        cv2.putText(frame_undist, 'kts = %.0f' % speed, (100, 150), font, 1.5, (0,255,0), 2,cv2.CV_AA)
        print lat_deg, lon_deg, altitude
        cv2.imshow('hud', frame_undist)
        if 0xFF & cv2.waitKey(5) == 27:
            break


# plot the data ...
plt.figure(1)
plt.ylabel('roll rate (deg per sec)')
plt.xlabel('flight time (sec)')
plt.plot(movie[:,0] + time_shift, movie[:,2]*r2d, label='estimate from flight movie')
if args.apm_log:
    plt.plot(flight_imu[:,0], flight_imu[:,3]*r2d, label='flight data log')
else:
    plt.plot(flight_imu[:,0], flight_imu[:,1]*r2d, label='flight data log')
#plt.plot(movie_interp[:,1])
#plt.plot(flight_interp[:,1])
plt.legend()

plt.figure(2)
plt.plot(ycorr)

plt.figure(3)
plt.ylabel('pitch rate (deg per sec)')
plt.xlabel('flight time (sec)')
plt.plot(movie[:,0] + time_shift, (movie[:,3]/qratio)*r2d, label='estimate from flight movie')
plt.plot(flight_imu[:,0], flight_imu[:,2]*r2d, label='flight data log')
#plt.plot(movie_interp[:,1])
#plt.plot(flight_interp[:,1])
plt.legend()

plt.figure(4)
plt.ylabel('yaw rate (deg per sec)')
plt.xlabel('flight time (sec)')
plt.plot(movie[:,0] + time_shift, (movie[:,4]/rratio)*r2d, label='estimate from flight movie')
plt.plot(flight_imu[:,0], flight_imu[:,3]*r2d, label='flight data log')
#plt.plot(movie_interp[:,1])
#plt.plot(flight_interp[:,1])
plt.legend()

plt.show()

#!/usr/bin/env python
import signal
import sys
import time
import argparse
import json
import requests
import datetime
from astral import Astral, Location
from ouimeaux.environment import Environment
from bluetooth import *


def should_update(sunset, early_offset_min):
    """
    Only run this script if the time is between SUNSET-EARLY_OFFSET_MINmin and 12AM
    """
    now = datetime.datetime.now(tz=sunset.tzinfo)
    midnight = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    if sunset - datetime.timedelta(minutes=early_offset_min) <= now <= midnight:
        return True
    return False


def connect_bt(addr):
    socket = BluetoothSocket(RFCOMM)
    try:
        socket.connect((addr, 1))
        print('Connected')
    except:
        return None
    return socket


def parse_config(filename):
    with open(filename) as f:
        d = json.load(f)
        print 'Loaded configuration options:'
        print '- Location: {}'.format(d['location'])
        print '- Polling interval: {} sec'.format(d['interval'])
        print '- Last detection timeout: {} min'.format(d['timeout'])
        print '- Bluetooth devices: {}'.format(', '.join(d['devices']['bluetooth']))
        print '- Wemo switch names: {}'.format(', '.join(d['devices']['switches']))
        return d


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', '-c', action='store', default='/etc/btdaemon.conf', help='Config file')
    args = parser.parse_args()

    config = parse_config(args.config)

    present = False
    running = True
    def handler(signum, frame):
        global running
        running = False
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)

    print 'Discovering WeMo devices...',
    env = Environment()
    sys.stdout.flush()
    env.start()
    env.discover(5)
    print 'Done.'

    switches = env.list_switches()
    if config['devices']['switches'][0] not in switches:
        print "Couldn't find switch named '{}'. Discovered switches: {}".format(config['devices']['switches'][0], ', '.join(switches))
        sys.exit(1)

    switch = env.get_switch(config['devices']['switches'][0])

    print 'Fetching geolocation...',
    sys.stdout.flush()
    geodata = requests.get('http://freegeoip.net/json/').json()
    location = Location((
        geodata['city'],
        geodata['region_name'],
        geodata['latitude'],
        geodata['longitude'],
        geodata['time_zone'], 0))
    print location.name
    print 'Starting...'

    last_on_time = 0
    socket = connect_bt(config['devices']['bluetooth'][0])
    while running:
        try:
            socket.send('0')
            present = True
        except BluetoothError:
            print('Disconnected')
            socket = None
        except AttributeError:
            pass
        finally:
            if not socket:
                socket = connect_bt(config['devices']['bluetooth'][0])

        sun = location.sun()
        sunset = sun['sunset']
        if should_update(sunset, config['offset']):
            if socket:
                switch.on()
                last_on_time = time.time()
            elif not socket and time.time() - last_on_time > config['timeout'] * 60:
                switch.off()

        time.sleep(config['interval'])

    print 'Caught signal... cleaning up'
    if socket:
        try:
            socket.close()
        except:
            pass
    print 'Done'

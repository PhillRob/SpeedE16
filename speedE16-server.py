#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import psutil
import subprocess
import os
import yaml
import ipaddress
import string
import random
import glob
import time

from flask import Flask
from flask import request
from flask import send_from_directory

from two1.commands.util import config
from two1.wallet.two1_wallet import Wallet
from two1.bitserv.flask import Payment
from two1.bitrequests import BitTransferRequests
from two1.bitrequests import BitRequestsError
requests = BitTransferRequests(Wallet(), config.Config().username)

from speedE16 import SpeedE16

app = Flask(__name__)

# Set the max upload size to 2 MB
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024

# setup wallet
wallet = Wallet()
payment = Payment(app, wallet)

# hide logging
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

dataDir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'server-data')


@app.route('/manifest')
def manifest():
    """
    Provide the app manifest to the 21 crawler.
    """
    with open('./manifest.yaml', 'r') as f:
        manifest = yaml.load(f)
    return json.dumps(manifest)


@app.route('/upload', methods=['POST'])
@payment.required(5)
def upload():
    """
    Upload a file in order for client to test upload speed.  File will be saved for later retrieval by client.
    """
    # First, clear out any old uploaded files that are older than an hour
    delete_before_time = time.time() - (60 * 60)
    files = glob.glob(os.path.join(dataDir, "*"))
    for file in files:
        if file.endswith(".md") is not True and os.path.isfile(file) is True:
            if os.path.getmtime(file) < delete_before_time:
                print("Removing old file: " + file)
                os.remove(file)

    # check if the post request has the file part
    if 'file' not in request.files:
        return json.dumps({'success': False, 'error': 'File Upload arg not found'}, indent=4, sort_keys=True), 400

    file = request.files['file']

    # if user does not select file, browser also submits an empty part without filename
    if file.filename == '':
        return json.dumps({'success': False, 'error': 'No selected file'}, indent=4, sort_keys=True), 400

    # Generate a random file name and save it
    filename = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(20))
    file.save(os.path.join(dataDir, filename))

    # Return the file name so the client knows what to request to test download
    return json.dumps({'success': True, 'filename': filename}, indent=4, sort_keys=True)


@app.route('/download')
@payment.required(5)
def download():
    """
    Downloads the file requested by the query param.

    Returns: HTTPResponse 200 the file payload.
    HTTP Response 404 if the file is not found.
    """
    # Build the path to the file from the current dir + data dir + requested file name
    requestedFile = request.args.get('file')
    filePath = os.path.join(dataDir, requestedFile)

    if os.path.isfile(filePath) is not True:
        return json.dumps({'success': False, 'error': 'Requested file not found'}, indent=4, sort_keys=True), 404

    return send_from_directory(dataDir, requestedFile)


@app.route('/remote')
@payment.required(10)
def remote():
    """ Downloads a file from a remote server and responds back with stats and sha256 of downloaded file.
        Payment required is 10 satoshis since it will cost 5 satoshis to download from the remote host

    Returns: HTTPResponse 200 the file payload is invalid.
    HTTP Response 404 if the file is not found.
    """

    print("Remote query requested.")

    # Build the path to the file from the current dir + data dir + requested file name
    requestedFile = request.args.get('file')
    requestedHost = request.args.get('host')

    print("Requesting file: " + requestedFile + " from host: " + requestedHost)

    # Create the speed testing client
    remoteBaseUrl = os.path.join(dataDir, "remote")
    speed = SpeedE16(remoteBaseUrl, "http://" + requestedHost + ":8016")

    downloadData = speed.download(requests, requestedFile)

    if downloadData['success'] == True:

        print("Download shows success")

        # Delete the file downloaded file since we don't need it anymore
        os.remove(downloadData['download_path'])
        print("Deleted the temp downloaded file: " + downloadData['download_path'])

    return json.dumps(downloadData, indent=4, sort_keys=True)


if __name__ == '__main__':
    import click

    @click.command()
    @click.option("-d", "--daemon", default=False, is_flag=True,
                  help="Run in daemon mode.")
    def run(daemon):
        if daemon:
            pid_file = './speedE16.pid'
            if os.path.isfile(pid_file):
                pid = int(open(pid_file).read())
                os.remove(pid_file)
                try:
                    p = psutil.Process(pid)
                    p.terminate()
                except:
                    pass
            try:
                p = subprocess.Popen(['python3', 'speedE16-server.py'])
                open(pid_file, 'w').write(str(p.pid))
            except subprocess.CalledProcessError:
                raise ValueError("error starting speedE16-server.py daemon")
        else:
            print("Server running...")
            app.run(host='0.0.0.0', port=8016)

    run()

#!/usr/bin/env python3

import rpyc
import subprocess
import os
import signal
from time import sleep
import sys

NUM_TRIES = 10

class WrapperService(rpyc.Service):
    def on_connect(self):
        pass

    def on_disconnect(self):
        pass

    def exposed_setup(self, exp_id, name, config_file, duration = 60, server_timeout = 10,
                      rpc_port = 5555, status_time_interval = 5, wait = False, single_server = 0,
                      taskset_schema = 0, client_taskset = False, recording_path = "", interest_txn = "NEW ORDER"):
        self.run_process = subprocess.Popen(['./dsef/run.py'])

        self.conn = None
        i = 0
        while self.conn == None:
            try:
                self.conn = rpyc.connect('localhost', 18860, config={'sync_request_timeout':60, 'allow_pickle':True})
                break
            except ConnectionRefusedError:
                if i < NUM_TRIES:
                    print("Failed to connect to run.py, trying again")
                    sleep(0.5)
                else:
                    print("Failed to connect. Aborting!")
                    raise ConnectionError
            i += 1

        self.root = self.conn.root
        print('Connected to process: {}'.format(self.run_process.pid))

        self.root.setup(exp_id, name, config_file, duration, server_timeout, rpc_port, status_time_interval, wait, single_server, taskset_schema, client_taskset, recording_path, interest_txn)

    def exposed_launch(self):
        self.root.launch()

    def exposed_run(self):
        return self.root.run()

    def exposed_teardown(self):
        self.root.teardown()

        self.conn.close()
        self.root = None
        self.run_process.kill()

    def exposed_stop(self):
        self.close()

if __name__ == "__main__":
    from rpyc.utils.server import *
    t = ThreadedServer(WrapperService, port = 18861, protocol_config = {'allow_pickle':True})
    print("Starting RPyC Server...")
    t.start()

#!/usr/bin/env python3
import rpyc
import logger
import sys

class ExperimentService(rpyc.Service):
    def on_connect(self):
        pass

    def on_disconnect(self):
        pass

    def exposed_setup(self, experiment_conf):
        pass

    def exposed_launch(self):
        pass

    def exposed_run(self):
        pass

    def exposed_teardown(self):
        pass

if __name__ == "__main__":
    from rpyc.utils.server import *
    t = ThreadedServer(ExperimentService, port = int(sys.argv[1]), protocol_config = {'allow_pickle':True})
    t.start()

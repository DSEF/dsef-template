#!/usr/bin/env python3
from pydsef import Service, Registry

@Registry.experiment
class MyExperiment(Service):
    @Registry.setup
    def setup(self, experiment_conf):
        pass

    @Registry.launch
    def launch(self):
        pass

    @Registry.run
    def run(self):
        pass

    @Registry.teardown
    def teardown(self):
        pass

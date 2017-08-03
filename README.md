# DSEF-template
(future abstract about what DSEF is)

## How to use
1. Clone this repository to a desired location within a Jupyter notebook server: `git clone git@github.com:DSEF/dsef-python.git`
2. Define python enumerations for desired experiment modes
3. Fill in Emulab information (this might work with other Testbeds, but it has only been tested with Emulab)
4. Define experiment related variables
5. Hosts is a file with the names of all the servers used in the experiment. This is a yaml cell.
6. Now it is the harder part :p
   - In the initialization cell, write a script that takes the set of experiment parameters and turns this into a list of experiments
   - Fill in the `run.py` script with the required steps
   
## Todo:
- [ ] Write better documentation
- [ ] Remove Janus specific stuff

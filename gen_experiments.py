#! /usr/bin/env python
import sys
import copy
import traceback
import os
import os.path
import tempfile
import subprocess
import itertools
import shutil
import glob
import signal
import shutil

from argparse import ArgumentParser
from logging import info, debug, error

# sys.path.insert(1, os.path.join(sys.path[0], '..'))
from placement_strategy import ClientPlacement, BalancedPlacementStrategy, LeaderPlacementStrategy

import logging
import yaml

DEFAULT_MODES = ["tpl_ww:multi_paxos",
                 "occ:multi_paxos",
                 "tapir:tapir",
                 "brq:brq"]

DEFAULT_CLIENTS = ["1:2"]
DEFAULT_SERVERS = ["1:2"]
DEFAULT_BENCHMARKS = [ "rw_benchmark", "tpccd" ]
DEFAULT_TRIAL_DURATION = 30
DEFAULT_EXECUTABLE = "./run.py"

APPEND_DEFAULTS = {
    'client_counts': DEFAULT_CLIENTS,
    'server_counts': DEFAULT_SERVERS,
    'benchmarks': DEFAULT_BENCHMARKS,
    'modes': DEFAULT_MODES,
}
TMP_DIR='./tmp'
FINAL_DIR='./dsef'

logger = logging.getLogger('')

def create_parser():
    parser = ArgumentParser()
    parser.add_argument(dest="experiment_name",
                        help="name of experiment")
    parser.add_argument('-e', "--executable", dest="executable",
                        help="the executable to run",
                        default = DEFAULT_EXECUTABLE)
    parser.add_argument("-c", "--client-count", dest="client_counts",
                        help="client counts; accpets " + \
                        "'<start>:<stop>:<step>' tuples with same semantics as " + \
                        "range builtin function.",
                        action='append',
                        default=[])
    parser.add_argument("-cl", "--client-load", dest="client_loads",
                        help="load generation for open clients",
                        nargs="+", type=int, default=[-1])
    parser.add_argument("-st", "--server-timeout", dest="s_timeout", default="30")
    parser.add_argument("-s", "--server-count", dest="server_counts",
                        help="client counts; accpets " + \
                        "'<start>:<stop>:<step>' tuples with same semantics as " + \
                        "range builtin function.",
                        action='append',
                        default =[])
    parser.add_argument("-z", "--zipf", dest="zipf", default=[None],
                        help="zipf values",
                        nargs="+", type=str)
    parser.add_argument("-d", "--duration", dest="duration",
                        help="trial duration",
                        type=int,
                        default = DEFAULT_TRIAL_DURATION)
    parser.add_argument("-r", "--replicas", dest="num_replicas",
                        help="number of replicas",
                        type=int,
                        default = 1)
    parser.add_argument('-b', "--benchmarks", dest="benchmarks",
                        help="the benchmarks to run",
                        action='append',
                        default =[])
    parser.add_argument("-m", "--modes", dest="modes",
                        help="Concurrency control modes; tuple '<cc-mode>:<ab-mode>'",
                        action='append',
                        default=[])
    parser.add_argument("-hh", "--hosts", dest="hosts_file",
                        help="path to file containing hosts yml config",
                        default='config/hosts.yml',
                        required=True)
    parser.add_argument("-cc", "--config", dest="other_config",
                        action='append',
                        default=[],
                        help="path to yml config (not containing processes)")
    parser.add_argument("-g", "--generate-graphs", dest="generate_graph",
                        action='store_true', default=False, help="generate graphs")
    parser.add_argument("-cp", "--client-placement", dest="client_placement",
                        choices=[ClientPlacement.BALANCED, ClientPlacement.WITH_LEADER],
                        default=ClientPlacement.BALANCED, help="client placement strategy (with leader for multipaxos)")
    parser.add_argument("-u", "--cpu-count", dest="cpu_count", type=int,
                        default=1, help="number of cores on the servers")
    parser.add_argument("-dc", "--data-centers", dest="data_centers", nargs="+", type=str,
                        default=[], help="data center names (for multi-dc setup)")
    parser.add_argument("--allow-client-overlap", dest="allow_client_overlap",
                        action='store_true', default=False, help="allow clients and server to be mapped to same machine (for testing locally)")
    return parser


def parse_commandline():
    args = create_parser().parse_args()
    for k,v in args.__dict__.iteritems():
        if k in APPEND_DEFAULTS and v == []:
            args.__dict__[k] = APPEND_DEFAULTS[k]
    return args.__dict__

def gen_experiment_suffix(b, m, c, z, cl):
    m = m.replace(':', '-')
    if z is not None:
        return "{}_{}_{}_{}_{}".format(b, m, c, z, cl)
    else:
        return "{}_{}_{}_{}".format(b, m, c, cl)

def get_range(r):
    a = []
    parts = r.split(':')
    for p in parts:
        a.append(int(p))
    if len(parts)==1:
        return range(a[0],a[0]+1)
    else:
        return range(*a)

def gen_process_and_site(args, experiment_name, num_c, num_s, num_replicas, hosts_config, mode):
    hosts = hosts_config['host']

    layout_strategies = {
        ClientPlacement.BALANCED: BalancedPlacementStrategy(),
        ClientPlacement.WITH_LEADER: LeaderPlacementStrategy(),
    }

    if False and mode.find('multi_paxos') >= 0:
        strategy = layout_strategies[ClientPlacement.WITH_LEADER]
    else:
        strategy = layout_strategies[ClientPlacement.BALANCED]

    layout = strategy.generate_layout(args, num_c, num_s, num_replicas, hosts_config)

    if not os.path.isdir(TMP_DIR):
        os.makedirs(TMP_DIR)

    if not os.path.isdir(FINAL_DIR):
        os.makedirs(FINAL_DIR)

    site_process_file = tempfile.NamedTemporaryFile(
        mode='w',
        prefix='janus-proc-{}'.format(experiment_name),
        suffix='.yml',
        dir=TMP_DIR,
        delete=False)

    contents = yaml.dump(layout, default_flow_style=False)

    result = None
    with site_process_file:
        site_process_file.write(contents)
        result = site_process_file.name

    return result

def load_config(fn):
    with open(fn, 'r') as f:
        contents = yaml.load(f)
        return contents

def modify_dynamic_params(args, benchmark, mode, abmode, zipf):
    configs = args["other_config"]
    configs.append("config/{}.yml".format(benchmark))

    if "{}:{}".format(mode, abmode) == "tapir:tapir": configs.append("config/tapir.yml")
    elif "{}:{}".format(mode, abmode) == "brq:brq": configs.append("config/brq.yml")
    elif "{}:{}".format(mode, abmode) == "occ:multi_paxos": configs.append("config/occ_paxos.yml")

    # for config in configs:
    #     modified = False

    #     output_config = config
    #     config = load_config(config)

    #     if 'bench' in config:
    #         if 'workload' in config['bench']:
    #             config['bench']['workload'] = benchmark
    #             modified = True
    #         if 'dist' in config['bench'] and zipf is not None:
    #             try:
    #                 zipf_value = float(zipf)
    #                 config['bench']['coefficient'] = zipf_value
    #                 config['bench']['dist'] = 'zipf'
    #             except ValueError:
    #                 config['bench']['dist'] = str(zipf)
    #             modified = True
    #     if 'mode' in config and 'cc' in config['mode']:
    #         config['mode']['cc'] = mode
    #         modified = True
    #     if 'mode' in config and 'ab' in config['mode']:
    #         config['mode']['ab'] = abmode
    #         modified = True

    #     if modified:
    #         f = tempfile.NamedTemporaryFile(
    #             mode='w',
    #             prefix='janus-other-{}'.format(args["experiment_name"]),
    #             suffix='.yml',
    #             dir=TMP_DIR,
    #             delete=False)
    #         output_config = f.name
    #         logger.debug("generated config: %s", output_config)
    #         contents = yaml.dump(config, default_flow_style=False)
    #         with f:
    #             f.write(contents)

    #     output_configs.append(output_config)
    return configs

def aggregate_configs(*args):
    logging.debug("aggregate configs: {}".format(args))
    config = {}
    for fn in args:
        config.update(load_config(fn))
    return config

def generate_config(args, experiment_name, benchmark, mode, zipf, client_load, num_client,
                    num_server, num_replicas):
    logger.debug("generate_config: {}, {}, {}, {}, {}".format(
        experiment_name, benchmark, mode, num_client, zipf))
    hosts_config = load_config(args["hosts_file"])
    proc_and_site_config = gen_process_and_site(args, experiment_name,
                                                num_client, num_server,
                                                num_replicas, hosts_config, mode)

    logger.debug("site and process config: %s", proc_and_site_config)
    cc_mode, ab_mode = mode.split(':')
    config_files = modify_dynamic_params(args, benchmark, cc_mode, ab_mode,
                                         zipf)
    config_files.insert(0, args["hosts_file"])
    config_files.append(proc_and_site_config)
    result = aggregate_configs(*config_files)

    if result['client']['type'] == 'open':
        if client_load == -1:
            logger.fatal("must set client load param for open clients")
            sys.exit(1)
        else:
            result['client']['rate'] = client_load

    with tempfile.NamedTemporaryFile(
            mode='w',
            prefix='janus-final-{}-'.format(args["experiment_name"]),
            suffix='.yml',
            dir=FINAL_DIR,
            delete=False) as f:
        f.write(yaml.dump(result))
        result = f.name.split("/")[-1]
        logger.info("result: %s", result)
    return os.path.join('dsef', result) #TODO: make the name dsef get passed in from Jupyter

def save_git_revision():
    rev_file = "/home/ubuntu/janus/build/revision.txt"
    if os.path.isfile(rev_file):
        cmd = "cat {}".format(rev_file)
        rev = subprocess.check_output(cmd, shell=True)
        return rev

    log_dir = "./log/"
    rev = None
    fn = "{}/revision.txt".format(log_dir)
    cmd = 'git rev-parse HEAD'
    with open(fn, 'w') as f:
        logger.info('running: {}'.format(cmd))
        rev = subprocess.check_output(cmd, shell=True)
        f.write(rev)
    return rev

exp_id = 0
def generate(args):
    # server_counts = itertools.chain.from_iterable([get_range(sr) for sr in args["server_counts"]])
    server_counts = itertools.chain(args['server_counts'])
    # client_counts = itertools.chain.from_iterable([get_range(cr) for cr in args["client_counts"]])
    client_counts = itertools.chain(args['client_counts'])

    experiment_params = (server_counts,
                         client_counts,
                         args["modes"],
                         args["benchmarks"],
                         args["zipf"],
                         args["client_loads"])

    experiments = itertools.product(*experiment_params)
    experiment_list = []
    for params in experiments:
        (num_server, num_client, mode, benchmark, zipf, client_load) = params
        experiment_suffix = gen_experiment_suffix(
            benchmark,
            mode,
            num_client,
            zipf,
            client_load)
        experiment_name = "{}-{}".format(
            args["experiment_name"],
            experiment_suffix)

        logger.info("Experiment: {}".format(params))
        config_file = generate_config(
            args,
            experiment_name,
            benchmark, mode,
            zipf,
            client_load,
            num_client,
            num_server,
            args["num_replicas"])

        # save_git_revision()
        global exp_id
        exp_id += 1
        experiment_list.append((exp_id, experiment_name, config_file))
        # scrape_data(experiment_name)
        # archive_results(experiment_name)

    # write_file(experiment_list, args['duration'], args["s_timeout"])
    return experiment_list

    # aggregate_results(experiment_name)
    # generate_graphs(args)

def construct_args(name, duration, hosts_file, client_counts, client_loads,
                  s_timeout, server_counts, zipf, num_replicas,
                  benchmarks, modes, client_placement,
                  cpu_count, data_centers, allow_client_overlap, other_config):
    args = dict()
    args["experiment_name"] = name
    args["duration"] = duration
    args["hosts_file"] = hosts_file
    args["client_counts"] = client_counts
    args["client_loads"] = client_loads
    args["s_timeout"] = s_timeout
    args["server_counts"] = server_counts
    args["zipf"] = zipf
    args["duration"] = duration
    args["num_replicas"] = num_replicas
    args["benchmarks"] = benchmarks
    args["modes"] = modes
    args["other_config"] = other_config
    args["client_placement"] = client_placement
    args["cpu_count"] = cpu_count
    args["data_centers"] = data_centers
    args["allow_client_overlap"] = allow_client_overlap
    return args

def print_args(args):
    for k,v in args.items():
        logger.debug("%s = %s", k, v)

def main(name, duration, hosts_file, client_counts, client_loads,
         s_timeout, server_counts, zipf, num_replicas,
         benchmarks, modes, client_placement,
         cpu_count, data_centers, allow_client_overlap, other_config=[]):
    logging.basicConfig(format="%(levelname)s : %(message)s")
    logger.setLevel(logging.DEBUG)

    global exp_id
    exp_id = 0

    # for b in benchmarks:
    #     other_config.append("config/{}.yml".format(b))

    # for m in modes:
    #     if m == "tapir:tapir": other_config.append("config/tapir.yml")
    #     if m == "brq:brq": other_config.append("config/brq.yml")
    #     if m == "occ:multi_paxos": other_config.append("config/occ_paxos.yml")

    args = construct_args(name, duration, hosts_file, client_counts, client_loads,
                          s_timeout, server_counts, zipf, num_replicas,
                          benchmarks, modes, client_placement,
                          cpu_count, data_centers, allow_client_overlap, other_config)
    print_args(args)
    res = None
    try:
        res = generate(args)
        shutil.rmtree(TMP_DIR)
    except Exception:
        traceback.print_exc()

    return res

if __name__ == "__main__":
    main()

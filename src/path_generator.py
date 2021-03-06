import yaml
import os
import networkx as nx
import pandas as pd
import numpy as np
import argparse as ap

from dqnroute.utils import *
from dqnroute.messages import Package

def main():
    parser = ap.ArgumentParser(description='Path CSV generator (without full emulation)')
    parser.add_argument('settings_file', metavar='settings_file', type=str,
                        help='Path to run settings file')
    parser.add_argument('logfile', metavar='logfile', type=str,
                        help='Path to results .csv')

    args = parser.parse_args()

    sfile = open(args.settings_file)
    run_params = yaml.safe_load(sfile)
    sfile.close()

    G = nx.Graph()
    links_data = {}
    for e in run_params['network']:
        u = e['u']
        v = e['v']
        w = e['latency']
        G.add_edge(u, v, weight=w)
        links_data[(u, v)] = e
    try:
        os.remove(args.logfile)
    except FileNotFoundError:
        pass

    logfile = open(args.logfile, 'a')

    settings = run_params['settings']
    df = pd.DataFrame(columns=get_data_cols(len(G.nodes())))
    s_delta = settings['synchronizer']['delta']
    outgoing_pkgs_nums = {}

    for (action, cur_time, params) in gen_network_actions(G.nodes(), settings['pkg_distr']):
        if action == 'send_pkg':
            pkg_id, s, d, size = params
            path = nx.dijkstra_path(G, s, d)
            time = cur_time + s_delta
            pkg = Package(pkg_id, size, d, time, 0, None)
            for (i, n) in enumerate(path):
                df.loc[len(df)] = mk_current_neural_state(G, time, pkg, n)
                if i < len(path) - 1:
                    time += G.get_edge_data(n, path[i+1])['weight']
            df.to_csv(logfile, header=False, index=False)
            df.drop(df.index, inplace=True)
            print("pkg #{} done".format(pkg_id))
        elif action == 'break_link':
            u, v = params
            G.remove_edge(u, v)
            print('removed link ({}, {})'.format(u, v))
        elif action == 'restore_link':
            u, v = params
            w = links_data[(u, v)]['latency']
            G.add_edge(u, v, weight=w)
            print('restored link ({}, {})'.format(u, v))
        else:
            raise Exception('Unexpected action type: ' + action)

    logfile.close()

if __name__ == '__main__':
    main()

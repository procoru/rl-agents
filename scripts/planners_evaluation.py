"""Usage: planners_evaluation.py [options]

Compare performances of several planners on random MDPs

Options:
  -h --help
  --generate <true or false>  Generate new data [default: True].
  --show <true_or_false>      Plot results [default: True].
  --data_path <path>          Specify output data file path [default: ./out/planners/data.csv].
  --plot_path <path>          Specify figure data file path [default: ./out/planners].
  --budgets <start,end,N>     Computational budgets available to planners, in logspace [default: 1,3,100].
  --seeds <(s,)n>             Number of evaluations of each configuration, with an optional first seed [default: 10].
  --processes <p>             Number of processes [default: 4]
  --chunksize <c>             Size of data chunks each processor receives
  --range <start:end>         Range of budgets to be plotted.
"""
from ast import literal_eval
from pathlib import Path

from docopt import docopt
from collections import OrderedDict
from itertools import product
from multiprocessing.pool import Pool

import gym
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from rl_agents.agents.common import load_environment, agent_factory

gamma = 0.9
K = 5
SEED_MAX = 1e9


def agent_configs():
    agents = {
        "random": {
            "__class__": "<class 'rl_agents.agents.simple.random.RandomUniformAgent'>"
        },
        "olop": {
            "__class__": "<class 'rl_agents.agents.tree_search.olop.OLOPAgent'>",
            "gamma": gamma,
            "max_depth": 10,
            "upper_bound": {
                "type": "hoeffding",
                "c": 4
            },
            "lazy_tree_construction": True,
            "continuation_type": "uniform"
        },
        "kl-olop": {
            "__class__": "<class 'rl_agents.agents.tree_search.olop.OLOPAgent'>",
            "gamma": gamma,
            "max_depth": 10,
            "upper_bound": {
                "type": "kullback-leibler",
                "c": 2
            },
            "lazy_tree_construction": True,
            "continuation_type": "uniform"
        },
        "kl-olop-1": {
            "__class__": "<class 'rl_agents.agents.tree_search.olop.OLOPAgent'>",
            "gamma": gamma,
            "max_depth": 10,
            "upper_bound": {
                "type": "kullback-leibler",
                "c": 1
            },
            "lazy_tree_construction": True,
            "continuation_type": "uniform"
        },
        "laplace": {
            "__class__": "<class 'rl_agents.agents.tree_search.olop.OLOPAgent'>",
            "gamma": gamma,
            "upper_bound": {
                "type": "laplace",
                "c": 2
            },
            "lazy_tree_construction": True,
            "continuation_type": "uniform"
        },
        "deterministic": {
            "__class__": "<class 'rl_agents.agents.tree_search.deterministic.DeterministicPlannerAgent'>",
            "gamma": gamma
        },
        "value_iteration": {
            "__class__": "<class 'rl_agents.agents.dynamic_programming.value_iteration.ValueIterationAgent'>",
            "gamma": gamma,
            "iterations": int(3 / (1 - gamma))
        }
    }
    return OrderedDict(agents)


def value_iteration():
    return {
        "__class__": "<class 'rl_agents.agents.dynamic_programming.value_iteration.ValueIterationAgent'>",
        "gamma": gamma,
        "iterations": int(3 / (1 - gamma))
    }


def evaluate(experiment):
    # Prepare workspace
    seed, budget, agent_config, env_config, path = experiment
    gym.logger.set_level(gym.logger.DISABLED)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Make environment
    env = load_environment(env_config)
    env.seed(seed)
    state = env.reset()

    # Make agent
    agent_name, agent_config = agent_config
    agent_config["budget"] = int(budget)
    agent_config["iterations"] = int(env.config["max_steps"])
    agent = agent_factory(env, agent_config)
    agent.seed(seed)

    # Plan
    print("Evaluating {} with budget {} on seed {}".format(agent_name, budget, seed))
    action = agent.act(state)

    # Display tree
    display_tree = False
    if display_tree and hasattr(agent, "planner"):
        from rl_agents.agents.tree_search.graphics import TreePlot
        TreePlot(agent.planner, max_depth=100).plot(
            path.parent / "trees" / "{}_n={}.svg".format(agent_name, budget), title=agent_name)

    # Get action-values
    values = agent_factory(env, value_iteration()).state_action_value()[env.mdp.state, :]

    # Save results
    result = {
        "agent": agent_name,
        "budget": budget,
        "seed": seed,
        "action_value": values[action],
        "value": np.amax(values),
        "action": action
    }
    df = pd.DataFrame.from_records([result])
    with open(path, 'a') as f:
        df.to_csv(f, sep=',', encoding='utf-8', header=f.tell() == 0, index=False)


def prepare_experiments(budgets, seeds, path):
    budgets = np.unique(np.logspace(*literal_eval(budgets)).astype(int))
    agents = agent_configs()

    seeds = seeds.split(",")
    first_seed = int(seeds[0]) if len(seeds) == 2 else np.random.randint(0, SEED_MAX, dtype=int)
    seeds_count = int(seeds[-1])
    seeds = (first_seed + np.arange(seeds_count)).tolist()
    envs = ['configs/FiniteMDPEnv/env_garnet.json']
    paths = [path]
    experiments = list(product(seeds, budgets, agents.items(), envs, paths))
    return experiments


def plot_all(data_path, plot_path, data_range):
    print("Reading data from {}".format(data_path))
    df = pd.read_csv(data_path)
    df = df[~df.agent.isin(['agent'])].apply(pd.to_numeric, errors='ignore')
    df["regret"] = df["value"] - df["action_value"]
    df["action"] = "a" + df["action"].astype(str)
    print("Number of seeds found: {}".format(df.seed.nunique()))

    fig, ax = plt.subplots()
    ax.set(xscale="log", yscale="log")
    if data_range:
        start, end = data_range.split(':')
        df = df[df["budget"].between(int(start), int(end))]
    sns.lineplot(x="budget", y="regret", ax=ax, hue="agent", data=df)
    regret_path = plot_path / "regret.png"
    fig.savefig(regret_path, bbox_inches='tight')
    print("Saving regret plot to {}".format(regret_path))

    df = df.sort_values(by=['action'])
    fig, ax = plt.subplots()
    ax.set(xscale="log")
    sns.catplot(x="budget", y="action", hue="agent", ax=ax, data=df, alpha=1)
    action_path = plot_path / "actions.png"
    fig.savefig(action_path, bbox_inches='tight')
    print("Saving plots to {}".format(action_path))


def main(args):
    if args["--generate"] == "True":
        experiments = prepare_experiments(args["--budgets"], args['--seeds'], args["--data_path"])
        chunksize = int(args["--chunksize"]) if args["--chunksize"] else args["--chunksize"]
        with Pool(processes=int(args["--processes"])) as p:
            p.map(evaluate, experiments, chunksize=chunksize)
    if args["--show"] == "True":
        plot_all(Path(args["--data_path"]), Path(args["--plot_path"]), args["--range"])


def olop_horizon(episodes, gamma):
    return int(np.ceil(np.log(episodes) / (2 * np.log(1 / gamma))))


def allocate(budget):
    if np.size(budget) > 1:
        episodes = np.zeros(budget.shape)
        horizon = np.zeros(budget.shape)
        for i in range(budget.size):
            episodes[i], horizon[i] = allocate(budget[i])
        return episodes, horizon
    else:
        budget = np.array(budget).item()
        for episodes in range(1, budget):
            if episodes * olop_horizon(episodes, gamma) > budget:
                episodes -= 1
                break
        horizon = olop_horizon(episodes, gamma)
        return episodes, horizon


def plot_budget(budget, episodes, horizon):
    plt.figure()
    plt.subplot(311)
    plt.plot(budget, episodes, '+')
    plt.legend(["M"])
    plt.subplot(312)
    plt.plot(budget, horizon, '+')
    plt.legend(["L"])
    plt.subplot(313)
    plt.plot(budget, horizon / K ** (horizon - 1))
    plt.legend(['Computational complexity ratio'])
    plt.show()


if __name__ == "__main__":
    arguments = docopt(__doc__)
    main(arguments)

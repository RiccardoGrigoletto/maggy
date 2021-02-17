#
#   Copyright 2020 Logical Clocks AB
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#

"""Utility helper module for maggy experiments.
"""
import json
import math
import numpy as np
import os

import numpy as np
from pyspark import TaskContext

from maggy import constants
from maggy.core import exceptions
from maggy.core.environment.singleton import EnvSing

DEBUG = True

# in case importing in %%local
try:
    from pyspark.sql import SparkSession
    from pyspark import SparkConf
except ImportError:
    pass


def log(msg):
    """
    Generic log function (in case logging is changed from stdout later)

    :param msg: The msg to log
    :type msg: str
    """
    if DEBUG:
        print(msg)


def num_executors(sc):
    """
    Get the number of executors configured for Jupyter

    :param sc: The SparkContext to take the executors from.
    :type sc: [SparkContext
    :return: Number of configured executors for Jupyter
    :rtype: int
    """

    return EnvSing.get_instance().get_executors(sc)


def get_partition_attempt_id():
    """Returns partitionId and attemptNumber of the task context, when invoked
    on a spark executor.
    PartitionId is ID of the RDD partition that is computed by this task.
    The first task attempt will be assigned attemptNumber = 0, and subsequent
    attempts will have increasing attempt numbers.
    Returns:
        partitionId, attemptNumber -- [description]
    """
    task_context = TaskContext.get()
    return task_context.partitionId(), task_context.attemptNumber()


def progress_bar(done, total):
    done_ratio = done / total
    progress = math.floor(done_ratio * 30)

    bar = "["

    for i in range(30):
        if i < progress:
            bar += "="
        elif i == progress:
            bar += ">"
        else:
            bar += "."

    bar += "]"
    return bar


def json_default_numpy(obj):
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    else:
        raise TypeError(
            "Object of type {0}: {1} is not JSON serializable".format(type(obj), obj)
        )


def finalize_experiment(
    experiment_json,
    metric,
    app_id,
    run_id,
    state,
    duration,
    logdir,
    best_logdir,
    optimization_key,
):
    EnvSing.get_instance().finalize_experiment(
        experiment_json,
        metric,
        app_id,
        run_id,
        state,
        duration,
        logdir,
        best_logdir,
        optimization_key,
    )


def build_summary_json(logdir):
    """Builds the summary json to be read by the experiments service."""
    combinations = []
    env = EnvSing.get_instance()
    for trial in env.ls(logdir):
        if env.isdir(trial):
            return_file = trial + "/.outputs.json"
            hparams_file = trial + "/.hparams.json"
            if env.exists(return_file) and env.exists(hparams_file):
                metric_arr = env._convert_return_file_to_arr(return_file)
                hparams_dict = _load_hparams(hparams_file)
                combinations.append({"parameters": hparams_dict, "outputs": metric_arr})

    return json.dumps({"combinations": combinations}, default=json_default_numpy)


def _load_hparams(hparams_file):
    """Loads the HParams configuration from a hparams file of a trial."""

    hparams_file_contents = EnvSing.get_instance().load(hparams_file)
    hparams = json.loads(hparams_file_contents)

    return hparams


def handle_return_val(return_val, log_dir, optimization_key, log_file):
    """Handles the return value of the user defined training function."""
    env = EnvSing.get_instance()

    env._upload_file_output(return_val, log_dir)

    # Return type validation
    if not optimization_key:
        raise ValueError("Optimization key cannot be None.")
    if not return_val:
        raise exceptions.ReturnTypeError(optimization_key, return_val)
    if not isinstance(return_val, constants.USER_FCT.RETURN_TYPES):
        raise exceptions.ReturnTypeError(optimization_key, return_val)
    if isinstance(return_val, dict) and optimization_key not in return_val:
        raise KeyError(
            "Returned dictionary does not contain optimization key with the "
            "provided name: {}".format(optimization_key)
        )

    # validate that optimization metric is numeric
    if isinstance(return_val, dict):
        opt_val = return_val[optimization_key]
    else:
        opt_val = return_val
        return_val = {optimization_key: opt_val}

    if not isinstance(opt_val, constants.USER_FCT.NUMERIC_TYPES):
        raise exceptions.MetricTypeError(optimization_key, opt_val)

    # for key, value in return_val.items():
    #    return_val[key] = value if isinstance(value, str) else str(value)

    return_val["log"] = log_file.replace(env.project_path(), "")

    return_file = log_dir + "/.outputs.json"
    env.dump(json.dumps(return_val, default=json_default_numpy), return_file)

    metric_file = log_dir + "/.metric"
    env.dump(json.dumps(opt_val, default=json_default_numpy), metric_file)

    return opt_val


def clean_dir(clean_dir, keep=[]):
    """Deletes all files in a directory but keeps a few."""
    env = EnvSing.get_instance()

    if not env.isdir(clean_dir):
        raise ValueError(
            "{} is not a directory. Use `hops.hdfs.delete()` to delete single "
            "files.".format(clean_dir)
        )
    for path in env.ls(clean_dir):
        if path not in keep:
            env.delete(path, recursive=True)


def validate_ml_id(app_id, run_id):
    """Validates if there was an experiment run previously from the same app id
    but from a different experiment (e.g. hops-util-py vs. maggy) module.
    """
    try:
        prev_ml_id = os.environ["ML_ID"]
    except KeyError:
        return app_id, run_id
    prev_app_id, _, prev_run_id = prev_ml_id.rpartition("_")
    if prev_run_id == prev_ml_id:
        # means there was no underscore found in string
        raise ValueError(
            "Found a previous ML_ID with wrong format: {}".format(prev_ml_id)
        )
    if prev_app_id == app_id and int(prev_run_id) >= run_id:
        return app_id, (int(prev_run_id) + 1)
    return app_id, run_id


def find_spark(conf=None):
    """
    Returns: SparkSession
    """
    # sp = SparkSession.builder.getOrCreate()
    # sp.stop()

    conf = SparkConf()
    conf.set("num-executors", "1")

    return (
        SparkSession.builder.getOrCreate()
        if not conf
        else SparkSession.builder.config(conf=conf).getOrCreate()
    )


def seconds_to_milliseconds(time):
    """
    Returns: time converted from seconds to milliseconds
    """
    return int(round(time * 1000))


def time_diff(t0, t1):
    """
    Args:
        :t0: start time in seconds
        :t1: end time in seconds

    Returns: string with time difference (i.e. t1-t0)

    """

    millis = seconds_to_milliseconds(t1) - seconds_to_milliseconds(t0)
    millis = int(millis)
    seconds = (millis / 1000) % 60
    seconds = int(seconds)
    minutes = (millis / (1000 * 60)) % 60
    minutes = int(minutes)
    hours = (millis / (1000 * 60 * 60)) % 24

    return "%d hours, %d minutes, %d seconds" % (hours, minutes, seconds)

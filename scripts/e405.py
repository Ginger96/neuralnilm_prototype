from __future__ import print_function, division
import matplotlib
import logging
from sys import stdout
matplotlib.use('Agg') # Must be before importing matplotlib.pyplot or pylab!
from neuralnilm import (Net, RealApplianceSource, 
                        BLSTMLayer, DimshuffleLayer, 
                        BidirectionalRecurrentLayer)
from neuralnilm.source import standardise, discretize, fdiff, power_and_fdiff
from neuralnilm.experiment import run_experiment, init_experiment
from neuralnilm.net import TrainingError
from neuralnilm.layers import MixtureDensityLayer
from neuralnilm.objectives import (scaled_cost, mdn_nll, 
                                   scaled_cost_ignore_inactive, ignore_inactive,
                                   scaled_cost3)
from neuralnilm.plot import MDNPlotter, CentralOutputPlotter
from neuralnilm.updates import clipped_nesterov_momentum

from lasagne.nonlinearities import sigmoid, rectify, tanh, identity
from lasagne.objectives import mse, binary_crossentropy
from lasagne.init import Uniform, Normal, Identity
from lasagne.layers import (LSTMLayer, DenseLayer, Conv1DLayer, 
                            ReshapeLayer, FeaturePoolLayer, RecurrentLayer)
from lasagne.layers.batch_norm import BatchNormLayer
from lasagne.updates import nesterov_momentum, momentum
from functools import partial
import os
import __main__
from copy import deepcopy
from math import sqrt
import numpy as np
import theano.tensor as T
import gc

"""
e400
'learn_init': False
independently_centre_inputs : True

e401
input is in range [0,1]
"""

NAME = os.path.splitext(os.path.split(__main__.__file__)[1])[0]
#PATH = "/homes/dk3810/workspace/python/neuralnilm/figures"
PATH = "/data/dk3810/figures"
SAVE_PLOT_INTERVAL = 500
GRADIENT_STEPS = 100

source_dict = dict(
    filename='/data/dk3810/ukdale.h5',
    appliances=[
        ['fridge freezer', 'fridge', 'freezer'], 
        'hair straighteners', 
        'television'
#        'dish washer',
#        ['washer dryer', 'washing machine']
    ],
    max_appliance_powers=[300, 500, 200, 2500, 2400],
    max_input_power=1000,
    on_power_thresholds=[5] * 5,
    min_on_durations=[60, 60, 60, 1800, 1800],
    min_off_durations=[12, 12, 12, 1800, 600],
    window=("2013-06-01", "2014-07-01"),
    seq_length=512,
#    random_window=64,
    output_one_appliance=False,
    boolean_targets=False,
    train_buildings=[1],
    validation_buildings=[1], 
#    skip_probability=0.9,
    one_target_per_seq=False,
    n_seq_per_batch=64,
    subsample_target=4,
    include_diff=False,
    include_power=True,
    clip_appliance_power=True,
    target_is_prediction=False,
#   independently_center_inputs=True,
#   standardise_input=True,
#    standardise_targets=True,
#    unit_variance_targets=True,
    input_padding=2,
    lag=0
#    classification=True
#    reshape_target_to_2D=True
    # input_stats={'mean': np.array([ 0.05526326], dtype=np.float32),
    #              'std': np.array([ 0.12636775], dtype=np.float32)},
    # target_stats={
    #     'mean': np.array([ 0.04066789,  0.01881946,  
    #                        0.24639061,  0.17608672,  0.10273963], 
    #                      dtype=np.float32),
    #     'std': np.array([ 0.11449792,  0.07338708,  
    #                    0.26608968,  0.33463112,  0.21250485], 
    #                  dtype=np.float32)}
)

N = 50
net_dict = dict(        
    save_plot_interval=SAVE_PLOT_INTERVAL,
#    loss_function=partial(ignore_inactive, loss_func=mdn_nll, seq_length=SEQ_LENGTH),
#    loss_function=lambda x, t: mdn_nll(x, t).mean(),
#    loss_function=lambda x, t: mse(x, t).mean(),
    loss_function=lambda x, t: binary_crossentropy(x, t).mean(),
#    loss_function=lambda x, t: binary_crossentropy(x, t).mean(),
#    loss_function=partial(scaled_cost, loss_func=mse),
#    loss_function=ignore_inactive,
#    loss_function=partial(scaled_cost3, ignore_inactive=False),
#    updates_func=momentum,
    updates_func=clipped_nesterov_momentum,
    updates_kwargs={'clip_range': (0, 10)},
    learning_rate=1e-1,
    learning_rate_changes_by_iteration={
        1000: 1e-2,
        2000: 1e-3
        # 800: 1e-4
#        500: 1e-3
       #  4000: 1e-03,
       # 6000: 5e-06,
       # 7000: 1e-06
       # 2000: 5e-06
        # 3000: 1e-05
        # 7000: 5e-06,
        # 10000: 1e-06,
        # 15000: 5e-07,
        # 50000: 1e-07
    },  
    do_save_activations=True,
#    auto_reshape=False,
#    plotter=CentralOutputPlotter
#    plotter=MDNPlotter
)




def exp_a(name):
    # tanh and softplus output
    # sane inits for other layers
    source_dict_copy = deepcopy(source_dict)
    source_dict_copy.update(dict(
        standardise_targets=True,
        unit_variance_targets=True
    ))
    source = RealApplianceSource(**source_dict_copy)
    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name,
        source=source,
        loss_function=lambda x, t: mse(x, t).mean(),
        learning_rate=1e-3,
        learning_rate_changes_by_iteration={
            1000: 1e-4,
            2000: 1e-5
        }
    ))
    net_dict_copy['layers_config']= [
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Uniform(25),
            'b': Uniform(25)
        },
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50)),
            'b': Normal(std=1/sqrt(50))
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 40,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': Conv1DLayer,
            'num_filters': 20,
            'filter_length': 4,
            'stride': 4,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50))
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 80,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DenseLayer,
            'num_units': source.n_outputs,
            'nonlinearity': T.nnet.softplus
        }
    ]
    net = Net(**net_dict_copy)
    net.load_params(2000)
    return net



def exp_b(name):
    # tanh and softplus output
    # sane inits for other layers
    # just large weights for first layer, sane biases
    source_dict_copy = deepcopy(source_dict)
    source_dict_copy.update(dict(
        standardise_targets=True,
        unit_variance_targets=True
    ))
    source = RealApplianceSource(**source_dict_copy)
    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name,
        source=source,
        loss_function=lambda x, t: mse(x, t).mean(),
        learning_rate=1e-3,
        learning_rate_changes_by_iteration={
            1000: 1e-4,
            2000: 1e-5
        }
    ))
    net_dict_copy['layers_config']= [
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Uniform(25),
            'b': Normal(std=1/sqrt(50))
        },
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50)),
            'b': Normal(std=1/sqrt(50))
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 40,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': Conv1DLayer,
            'num_filters': 20,
            'filter_length': 4,
            'stride': 4,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50))
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 80,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DenseLayer,
            'num_units': source.n_outputs,
            'nonlinearity': T.nnet.softplus
        }
    ]
    net = Net(**net_dict_copy)
    return net


def exp_c(name):
    # tanh and softplus output
    # sane inits for other layers
    # just large biases for first layer, sane weights
    source_dict_copy = deepcopy(source_dict)
    source_dict_copy.update(dict(
        standardise_targets=True,
        unit_variance_targets=True
    ))
    source = RealApplianceSource(**source_dict_copy)
    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name,
        source=source,
        loss_function=lambda x, t: mse(x, t).mean(),
        learning_rate=1e-3,
        learning_rate_changes_by_iteration={
            1000: 1e-4,
            2000: 1e-5
        }
    ))
    net_dict_copy['layers_config']= [
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'b': Uniform(25),
            'W': Normal(std=1/sqrt(50))
        },
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50)),
            'b': Normal(std=1/sqrt(50))
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 40,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': Conv1DLayer,
            'num_filters': 20,
            'filter_length': 4,
            'stride': 4,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50))
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 80,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DenseLayer,
            'num_units': source.n_outputs,
            'nonlinearity': T.nnet.softplus
        }
    ]
    net = Net(**net_dict_copy)
    return net



def exp_d(name):
    # tanh and softplus output
    # sane inits for other layers
    # batch norm
    source_dict_copy = deepcopy(source_dict)
    source_dict_copy.update(dict(
        standardise_targets=True,
        unit_variance_targets=True
    ))
    source = RealApplianceSource(**source_dict_copy)
    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name,
        source=source,
        loss_function=lambda x, t: mse(x, t).mean(),
        learning_rate=1e-3,
        learning_rate_changes_by_iteration={
            1000: 1e-4,
            2000: 1e-5
        }
    ))
    net_dict_copy['layers_config']= [
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': identity,
            'W': Uniform(25),
            'b': Uniform(25)
        },
        {
            'type': BatchNormLayer,
            'axes': (0, 1),
            'nonlinearity': tanh
        },
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': identity,
            'W': Normal(std=1/sqrt(50)),
            'b': Normal(std=1/sqrt(50))
        },
        {
            'type': BatchNormLayer,
            'axes': (0, 1),
            'nonlinearity': tanh
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 40,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh, # need nonlinearity for hid_to_hid
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': BatchNormLayer,
            'axes': (0, 1),
            'nonlinearity': identity
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': Conv1DLayer,
            'num_filters': 20,
            'filter_length': 4,
            'stride': 4,
            'nonlinearity': identity,
            'W': Normal(std=1/sqrt(50))
        },
        {
            'type': BatchNormLayer,
            'nonlinearity': tanh
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 80,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': BatchNormLayer,
            'nonlinearity': tanh,
            'axes': (0, 1)
        },
        {
            'type': DenseLayer,
            'num_units': source.n_outputs,
            'nonlinearity': T.nnet.softplus
        }
    ]
    net = Net(**net_dict_copy)
    return net


def exp_e(name):
    # like a but with max power = 5900W
    # tanh and softplus output
    # sane inits for other layers
    source_dict_copy = deepcopy(source_dict)
    source_dict_copy.update(dict(
        standardise_targets=True,
        unit_variance_targets=True,
        max_input_power=5900
    ))
    source = RealApplianceSource(**source_dict_copy)
    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name,
        source=source,
        loss_function=lambda x, t: mse(x, t).mean(),
        learning_rate=1e-3,
        learning_rate_changes_by_iteration={
            1000: 1e-4,
            2000: 1e-5
        }
    ))
    net_dict_copy['layers_config']= [
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Uniform(25),
            'b': Uniform(25)
        },
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50)),
            'b': Normal(std=1/sqrt(50))
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 40,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': Conv1DLayer,
            'num_filters': 20,
            'filter_length': 4,
            'stride': 4,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50))
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 80,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DenseLayer,
            'num_units': source.n_outputs,
            'nonlinearity': T.nnet.softplus
        }
    ]
    net = Net(**net_dict_copy)
    return net




def exp_f(name):
    # like a but with max power = 5900W and 5 appliances
    # tanh and softplus output
    # sane inits for other layers
    source_dict_copy = deepcopy(source_dict)
    source_dict_copy.update(dict(
        standardise_targets=True,
        unit_variance_targets=True,
        max_input_power=5900
    ))
    source_dict_copy['appliances'] = [
            ['fridge freezer', 'fridge', 'freezer'], 
            'hair straighteners', 
            'television',
            'dish washer',
            ['washer dryer', 'washing machine']
        ]

    source = RealApplianceSource(**source_dict_copy)
    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name,
        source=source,
        loss_function=lambda x, t: mse(x, t).mean(),
        learning_rate=1e-3,
        learning_rate_changes_by_iteration={
            1000: 1e-4,
            2000: 1e-5
        }
    ))
    net_dict_copy['layers_config']= [
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Uniform(25),
            'b': Uniform(25)
        },
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50)),
            'b': Normal(std=1/sqrt(50))
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 40,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': Conv1DLayer,
            'num_filters': 20,
            'filter_length': 4,
            'stride': 4,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50))
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 80,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DenseLayer,
            'num_units': source.n_outputs,
            'nonlinearity': T.nnet.softplus
        }
    ]
    net = Net(**net_dict_copy)
    net.load_params(1000)
    return net




def exp_g(name):
    # like a but with max power = 1000W and 5 appliances
    # tanh and softplus output
    # sane inits for other layers
    source_dict_copy = deepcopy(source_dict)
    source_dict_copy.update(dict(
        standardise_targets=True,
        unit_variance_targets=True,
        max_input_power=1000
    ))
    source_dict_copy['appliances'] = [
            ['fridge freezer', 'fridge', 'freezer'], 
            'hair straighteners', 
            'television',
            'dish washer',
            ['washer dryer', 'washing machine']
        ]
    source = RealApplianceSource(**source_dict_copy)
    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name,
        source=source,
        loss_function=lambda x, t: mse(x, t).mean(),
        learning_rate=1e-3,
        learning_rate_changes_by_iteration={
            1000: 1e-4,
            2000: 1e-5
        }
    ))
    net_dict_copy['layers_config']= [
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Uniform(25),
            'b': Uniform(25)
        },
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50)),
            'b': Normal(std=1/sqrt(50))
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 40,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': Conv1DLayer,
            'num_filters': 20,
            'filter_length': 4,
            'stride': 4,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50))
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 80,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DenseLayer,
            'num_units': source.n_outputs,
            'nonlinearity': T.nnet.softplus
        }
    ]
    net = Net(**net_dict_copy)
    return net



def exp_h(name):
    # like a but with max power = 5900W and 5 appliances
    # tanh and softplus output
    # sane inits for other layers
    source_dict_copy = deepcopy(source_dict)
    source_dict_copy.update(dict(
        standardise_targets=True,
        unit_variance_targets=True,
        max_input_power=5900,
        skip_probability=0.9
    ))
    source_dict_copy['appliances'] = [
            ['fridge freezer', 'fridge', 'freezer'], 
            'hair straighteners', 
            'television',
            'dish washer',
            ['washer dryer', 'washing machine']
        ]

    source = RealApplianceSource(**source_dict_copy)
    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name,
        source=source,
        loss_function=lambda x, t: mse(x, t).mean(),
        learning_rate=1e-3,
        learning_rate_changes_by_iteration={
            1000: 1e-4,
            2000: 1e-5
        }
    ))
    net_dict_copy['layers_config']= [
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Uniform(25),
            'b': Uniform(25)
        },
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50)),
            'b': Normal(std=1/sqrt(50))
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 40,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': Conv1DLayer,
            'num_filters': 20,
            'filter_length': 4,
            'stride': 4,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50))
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 80,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DenseLayer,
            'num_units': source.n_outputs,
            'nonlinearity': T.nnet.softplus
        }
    ]
    net = Net(**net_dict_copy)
    return net




def exp_i(name):
    # like a but with max power = 1000W and 5 appliances
    # tanh and softplus output
    # sane inits for other layers
    source_dict_copy = deepcopy(source_dict)
    source_dict_copy.update(dict(
        standardise_targets=True,
        unit_variance_targets=True,
        max_input_power=1000,
        skip_probability=0.9
    ))
    source_dict_copy['appliances'] = [
            ['fridge freezer', 'fridge', 'freezer'], 
            'hair straighteners', 
            'television',
            'dish washer',
            ['washer dryer', 'washing machine']
        ]
    source = RealApplianceSource(**source_dict_copy)
    net_dict_copy = deepcopy(net_dict)
    net_dict_copy.update(dict(
        experiment_name=name,
        source=source,
        loss_function=lambda x, t: mse(x, t).mean(),
        learning_rate=1e-3,
        learning_rate_changes_by_iteration={
            1000: 1e-4,
            2000: 1e-5
        }
    ))
    net_dict_copy['layers_config']= [
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Uniform(25),
            'b': Uniform(25)
        },
        {
            'type': DenseLayer,
            'num_units': 50,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50)),
            'b': Normal(std=1/sqrt(50))
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 40,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': Conv1DLayer,
            'num_filters': 20,
            'filter_length': 4,
            'stride': 4,
            'nonlinearity': tanh,
            'W': Normal(std=1/sqrt(50))
        },
        {
            'type': DimshuffleLayer,
            'pattern': (0, 2, 1)
        },
        {
            'type': BidirectionalRecurrentLayer,
            'num_units': 80,
            'W_in_to_hid': Normal(std=1/sqrt(50)),
            'gradient_steps': GRADIENT_STEPS,
            'nonlinearity': tanh,
            'learn_init': False, 
            'precompute_input': False
        },
        {
            'type': DenseLayer,
            'num_units': source.n_outputs,
            'nonlinearity': T.nnet.softplus
        }
    ]
    net = Net(**net_dict_copy)
    return net






def main():
    #     EXPERIMENTS = list('abcdefghijklmnopqrstuvwxyz')
#    EXPERIMENTS = list('abcdefghi')
    EXPERIMENTS = list('fghi')
    for experiment in EXPERIMENTS:
        full_exp_name = NAME + experiment
        func_call = init_experiment(PATH, experiment, full_exp_name)
        logger = logging.getLogger(full_exp_name)
        try:
            net = eval(func_call)
            run_experiment(net, epochs=5000)
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt")
            break
        except Exception as exception:
            logger.exception("Exception")
            # raise
        else:
            del net.source.train_activations
            gc.collect()
        finally:
            logging.shutdown()


if __name__ == "__main__":
    main()

'''
A second test for the curious uncertainty loop.
This one's for cluster training, not local.
'''

import sys
sys.path.append('curiosity')
sys.path.append('tfutils')
import tensorflow as tf

from curiosity.interaction import train, environment
from curiosity.interaction.models import another_sample_cfg
from tfutils import base, optimizer
import numpy as np
import os

NUM_BATCHES_PER_EPOCH = 1e8
RENDER2_HOST_ADDRESS = '10.102.2.162'

EXP_ID = 'marioish3'
CACHE_ID_PREFIX = '/mnt/fs0/nhaber/cache'
CACHE_DIR = os.path.join(CACHE_ID_PREFIX, EXP_ID)
if not os.path.exists(CACHE_DIR):
	os.mkdir(CACHE_DIR)

cfg = {
				'world_model' : {
					'state_shape' : [2, 64, 64, 3],
					'action_shape' : [2, 8]
				},
				'uncertainty_model' : {
					'state_shape' : [2, 64, 64, 3],
					'action_dim' : 8,
					'n_action_samples' : 50,
					'encode' : {
						'encode_depth' : 5,
						'encode' : {
							1 : {'conv' : {'filter_size' : 3, 'stride' : 2, 'num_filters' : 20}},
							2 : {'conv' : {'filter_size' : 3, 'stride' : 1, 'num_filters' : 20}},
							3 : {'conv' : {'filter_size' : 3, 'stride' : 2, 'num_filters' : 20}},
							4 : {'conv' : {'filter_size' : 3, 'stride' : 1, 'num_filters' : 10}},
							5 : {'conv' : {'filter_size' : 3, 'stride' : 2, 'num_filters' : 5}},
						}
					},
					'mlp' : {
						'hidden_depth' : 2,
						'hidden' : {1 : {'num_features' : 20, 'dropout' : .75},
									2 : {'num_features' : 1, 'activation' : 'identity'}
						}		
					},
					'loss_factor' : 100.
				},
				'seed' : 0
}

params = {

	'save_params' : {	
		'host' : 'localhost',
		'port' : 27017,
		'dbname' : 'uncertain_agent',
		'collname' : 'uniform_action',
		'exp_id' : EXP_ID,
		'save_valid_freq' : 2000,
        'save_filters_freq': 30000,
        'cache_filters_freq': 20000,
        'save_initial_filters' : False,
	'cache_dir' : CACHE_DIR,
        'save_to_gfs' : ['encoding_i', 'encoding_f', 'act_pred', 'fut_pred', 'batch']
	},


#	'load_params' : {
#		'exp_id' : ',
#		'load_param_dict' : None
#	},



	'what_to_save_params' : {
	        'big_save_keys' : ['fut_loss', 'act_loss', 'um_loss', 'encoding_i', 'encoding_f', 'act_pred', 'fut_pred'],
	        'little_save_keys' : ['fut_loss', 'act_loss', 'um_loss'],
		'big_save_len' : 100,
		'big_save_freq' : 10000
	},

	'model_params' : {
		'func' : train.get_latent_models,
 		'cfg' : cfg,
 		'action_model_desc' : 'uncertainty_model'
	},

	'data_params' : {
		'func' : train.get_default_data_provider,
		'action_limits' : np.array([1., 1.] + [80. for _ in range(6)]),
		'environment_params' : {
			'random_seed' : 1,
			'unity_seed' : 1,
			'room_dims' : (5., 5.),
			'state_memory_len' : {
					'depths1' : 3
				},
			'rescale_dict' : {
					'depths1' : (64, 64)
				},
			'USE_TDW' : True,
			'host_address' : RENDER2_HOST_ADDRESS
		},
		'scene_list' : [environment.example_scene_info],
		'scene_lengths' : [1024 * 32],
		'capacity' : 5
	},

	'train_params' : {
		'updater_func' : train.get_latent_updater
	},



	'optimizer_params' : {
		'world_model' : {
			'act_model' : {
				'func': optimizer.ClipOptimizer,
				'optimizer_class': tf.train.AdamOptimizer,
				'clip': True,
			},
			'fut_model' : {
                                'func': optimizer.ClipOptimizer,
                                'optimizer_class': tf.train.AdamOptimizer,
                                'clip': True,
                }
		},
		'uncertainty_model' : {
			'func': optimizer.ClipOptimizer,
			'optimizer_class': tf.train.AdamOptimizer,
			'clip': True,
		}

	},

	'learning_rate_params' : {
		'world_model' : {
			'act_model' : {
			'func': tf.train.exponential_decay,
			'learning_rate': 1e-5,
			'decay_rate': 1.,
			'decay_steps': NUM_BATCHES_PER_EPOCH,  # exponential decay each epoch
			'staircase': True
			},
			'fut_model' : {
                        'func': tf.train.exponential_decay,
                        'learning_rate': 1e-5,
                        'decay_rate': 1.,
                        'decay_steps': NUM_BATCHES_PER_EPOCH,  # exponential decay each epoch
                        'staircase': True
                }
		},
		'uncertainty_model' : {
			'func': tf.train.exponential_decay,
			'learning_rate': 1e-5,
			'decay_rate': 1.,
			'decay_steps': NUM_BATCHES_PER_EPOCH,  # exponential decay each epoch
			'staircase': True
		}
	},


}


if __name__ == '__main__':
#	raise Exception('FIX TFUTILS TRAINING SAVE')
	os.environ['CUDA_VISIBLE_DEVICES'] = sys.argv[1]
	train.train_from_params(**params)








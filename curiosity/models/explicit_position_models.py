'''
Architectures for explicit position prediction task.
'''

import numpy as np
import tensorflow as tf


from curiosity.models.model_building_blocks import ConvNetwithBypasses

def hidden_loop_with_bypasses(input_node, m, cfg, nodes_for_bypass = [], stddev = .01, reuse_weights = False, activation = 'relu'):
	assert len(input_node.get_shape().as_list()) == 2, len(input_node.get_shape().as_list())
	hidden_depth = cfg['hidden_depth']
	m.output = input_node
	print('in hidden loop')
	print(m.output)
	for i in range(1, hidden_depth + 1):
		with tf.variable_scope('hidden' + str(i)) as scope:
			if reuse_weights:
				scope.reuse_variables()
			bypass = cfg['hidden'][i].get('bypass')
			if bypass:
				bypass_node = nodes_for_bypass[bypass]
				m.add_bypass(bypass_node)
			nf = cfg['hidden'][i]['num_features']
			m.fc(nf, init = 'trunc_norm', activation = activation, bias = .01, stddev = stddev, dropout = None)
			nodes_for_bypass.append(m.output)
			print(m.output)
	return m.output

def position_only_mlp(inputs, cfg = None, T_in = 3, T_out = 3, num_points = 50, stddev = .01, activation = 'relu', **kwargs):
	input_shape = inputs['positions'].get_shape().as_list()
	assert len(input_shape) == 2
	assert input_shape[1] == (T_in + T_out) * 3 * num_points, (T_in, T_out, num_points, input_shape[1])
	current_node = inputs['positions'][:, :T_in * 3 * num_points]
	future_node = inputs['positions'][:, T_in * 3 * num_points : ]

	m = ConvNetwithBypasses(**kwargs)
	hidden_loop_with_bypasses(current_node, m, cfg, activation = activation, stddev = stddev)
	num_end_features = T_out * 3 * num_points
	with tf.variable_scope('out'):
		m.fc(num_end_features, init = 'trunc_norm', activation = None, bias = .01, stddev = stddev, dropout = None)

	print(m.output)
	return {'pred' : m.output, 'tv' : future_node}, m.params

def position_only_with_skip(inputs, cfg = None, T_in = 3, T_out = 3, skip = 0, num_points = 50, stddev = .01, activation = 'relu', **kwargs):
	input_shape = inputs['positions'].get_shape().as_list()
	assert len(input_shape) == 2
	assert input_shape[1] == (T_in + skip + T_out) * 3 * num_points, (T_in, T_out, num_points, input_shape[1])
	current_node = inputs['positions'][:, :T_in * 3 * num_points]
	future_node = inputs['positions'][:, -T_out * 3 * num_points : ]

	m = ConvNetwithBypasses(**kwargs)
	hidden_loop_with_bypasses(current_node, m, cfg,	activation = activation, stddev = stddev)
	with tf.variable_scope('out'):
		num_end_features = T_out * 3 * num_points
		m.fc(num_end_features, init = 'trunc_norm', activation = None, bias = .01, dropout = None, stddev = stddev)

	return {'pred' : m.output, 'tv' : future_node, 'in_pos' : current_node}, m.params

def positions_and_actions(inputs, cfg = None, T_in = 3, T_out = 3, skip = 0, num_points = 50, stddev = .01, activation = 'relu', **kwargs):
	input_shape = inputs['positions'].get_shape().as_list()
	assert len(input_shape) == 2
	assert input_shape[1] == (T_in + skip + T_out) * 3 * num_points, (T_in, T_out, num_points, input_shape[1])
	current_node = inputs['positions'][:, :T_in * 3 * num_points]
	future_node = inputs['positions'][:, -T_out * 3 * num_points : ]
	action_node = inputs['corresponding_actions']

	concat_node = tf.concat(1, [current_node, action_node])
	m = ConvNetwithBypasses(**kwargs)
	hidden_loop_with_bypasses(concat_node, m, cfg, activation = activation, stddev = stddev)
	print('final stretch')
	print(m.output)
	with tf.variable_scope('out'):
		num_end_features = T_out * 3 * num_points
		m.fc(num_end_features, init = 'trunc_norm', activation = None, bias = .01, stddev = stddev, dropout = None)
	print(m.output)
	return {'pred' : m.output, 'tv' : future_node, 'in_pos' : current_node}, m.params

def variable_skip_mlp(inputs, cfg = None, stddev = .01, activation ='relu', **kwargs):
	current_node = inputs['pos_in']
	future_node = inputs['pos_out']
	actions_node = inputs['corresponding_actions']
	skip_node = tf.cast(inputs['skip'], tf.float32)

	concat_node = tf.concat(1, [current_node, actions_node, skip_node])
	m = ConvNetwithBypasses(**kwargs)
	hidden_loop_with_bypasses(concat_node, m, cfg, activation = activation, stddev = stddev)
	with tf.variable_scope('out'):
		num_end_features = future_node.get_shape().as_list()[-1]
		m.fc(num_end_features, init = 'trunc_norm', activation = None, bias = .01, stddev = stddev, dropout = None)
	return {'pred' : m.output, 'tv' : future_node, 'in_pos' : current_node, 'skip' : skip_node}, m.params

def variable_skip_square(inputs, cfg = None, stddev = .01, **kwargs):
	current_node = inputs['pos_in']
	future_node = inputs['pos_out']
	actions_node = inputs['corresponding_actions']
	skip_node = tf.cast(inputs['skip'], tf.float32)

	concat_node = tf.concat(1, [current_node, actions_node, skip_node])
	m = ConvNetwithBypasses(**kwargs)
	m.output = concat_node


	num_first_layer = cfg['first_lin']
	with tf.variable_scope('first_lin'):
		m.fc(num_first_layer, init = 'trunc_norm', activation = None, bias = .01, dropout = None, stddev = stddev)

	#now square it!
	m.output = tf.concat(1, [m.output, m.output * m.output])
	print(m.output)

	num_end_features = future_node.get_shape().as_list()[1]
	with tf.variable_scope('out'):
		m.fc(num_end_features, init = 'trunc_norm', activation = None, bias = .01, dropout = None, stddev = stddev)

	print(m.output)
	return {'pred' : m.output, 'tv' : future_node, 'in_pos' : current_node, 'skip' : skip_node}, m.params


def l2_loss_fn(outputs, images, **kwargs):
	pred = outputs['pred']
	tv = outputs['tv']
	my_shape = tv.get_shape().as_list()
	norm = my_shape[0] * my_shape[1]
	return tf.nn.l2_loss(pred - tv) / norm

def compute_diffs(last_known_positions, subsequent_positions, t_in, t_out, num_points):
	curr_pos = last_known_positions
	diffs = []
	for i in range(t_out):
		next_pos = subsequent_positions[:, i * 3 * num_points : (i + 1) * 3 * num_points]
		diffs.append(next_pos - curr_pos)
		curr_pos = next_pos
	return tf.concat(1, diffs)

def l2_diff_loss_fn(outputs, positions_parsed, t_in = 3, t_out = 3, **kwargs):
	pred = outputs['pred']
	tv = outputs['tv']
	n_points = positions_parsed.get_shape().as_list()[-1] / (3 * (t_in + t_out))
	last_positions = positions_parsed[:, (t_in - 1) * 3 * n_points : t_in * 3 * n_points]
	diff = compute_diffs(last_positions, tv, t_in, t_out, n_points)
	return tf.nn.l2_loss(pred -  diff) / n_points

def l2_diff_loss_fn_w_skip(outputs, positions_parsed, t_in = 3, t_out = 3, num_points = 50):
	pred = outputs['pred']
	tv = outputs['tv']
	in_pos = outputs['in_pos']
	last_positions = in_pos[:, - 3 * num_points :]
	diff = compute_diffs(last_positions, tv, t_in, t_out, num_points)
	return tf.nn.l2_loss(pred - diff) / num_points





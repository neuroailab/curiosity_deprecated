"""
coupled symmetric model with from-below coupling
     --top-down is freely parameterized num-channels but from-below and top-down have same spatial extent 
     --top-down and bottom-up are combined via convolution to the correct num-channel shape:
        I = ReluConv(concat(top_down, bottom_up))
     --error is compuated as:
       (future_bottom_up - current_I)**2
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import tensorflow as tf
from curiosity.models.model_building_blocks import ConvNetwithBypasses
import curiosity.models.get_parameters as gp

DEBUG = True

def actionPredModel(inputs, min_time_difference, **kwargs):
    batch_size = inputs['images'].get_shape().as_list()[0]
    new_inputs = {'current' : inputs['images'], \
                  'actions' : inputs['parsed_actions'], \
                  'future' : inputs['future_images'], \
                  'times' : tf.ones([batch_size, min_time_difference])}
    return actionPredictionModelBase(new_inputs, **kwargs)

def actionPredictionModelBase(inputs, 
                        rng, 
                        cfg = {}, 
                        train = True, 
                        slippage = 0, 
                        minmax_end = True,
                        num_classes = None,
                        n_channels = 3,
                        **kwargs):
    '''
    Action Prediction Network Model Definition:

    current_images --> ENCODE -->  
                                CONCAT --> HIDDEN --> ACTIONS_PRED <-- ACTIONS_GT
    future_images  --> ENCODE --> 

    INPUT ARGUMENTS:
    inputs: {'current': images, 'future': images, 'actions': actions taken, 
             'times': time differences},
    rng: random number generator,
    cng: model definition,
    train: train model
    slippage: probability of random model changes
    min_max_end: use minmax clipping on last layer

    Outputs: dict with keys, pred and future, within those, dicts 
    with keys predi and futurei for i in 0:encode_depth, to be matched up in loss.
    '''


###### PREPROCESSING ######

    #set inputs
    current_node = inputs['current']
    future_node = inputs['future']
    actions_node = inputs['actions']
    time_node = inputs['times']

    #normalize and cast 
    current_node = tf.divide(tf.cast(current_node, tf.float32), 255)
    future_node = tf.divide(tf.cast(future_node, tf.float32), 255)
    actions_node = tf.cast(actions_node, tf.float32)
    original_actions = actions_node

    if(DEBUG):
        print('Actions shape')
        print(actions_node.get_shape().as_list())

    #init randon number generator
    if rng is None:
        rng = np.random.RandomState(seed=kwargs['seed'])

    #init ConvNet
    net = ConvNetwithBypasses(**kwargs)


####### ENCODING #######

    encode_depth = gp.getEncodeDepth(rng, cfg, slippage=slippage)
  
    if(DEBUG):
        print('Encode depth: %d' % encode_depth)
  
    cfs0 = None

    # Split current nodes
    shape = current_node.get_shape().as_list()
    dim = int(shape[3] / n_channels)
    current_nodes = []
    for d in range(dim):
        current_nodes.append(tf.slice(current_node, [0,0,0,d*n_channels], [-1,-1,-1,n_channels]))

    encode_nodes_current = [current_nodes]
    encode_nodes_future = [future_node]


    with tf.contrib.framework.arg_scope([net.conv, net.fc], \
                  init='trunc_norm', stddev=.01, bias=0, activation='relu'): 
        for i in range(1, encode_depth + 1):
            with tf.variable_scope('encode' + str(i)) as encode_scope:
                #get encode parameters 
                #cfs: conv filter size, nf: number of filters, cs: conv stride
                #pfs: pool filter size, ps: pool stride, pool_type: pool type
                cfs, nf, cs, do_pool, pfs, ps, pool_type = gp.getEncodeParam(i, \
                        encode_depth, rng, cfg, prev=cfs0, slippage=slippage)
                cfs0 = cfs

                new_encode_nodes_current = []
                for encode_node_current in encode_nodes_current[i - 1]:
                    #encode current images (conv + pool)
                    new_encode_node_current = net.conv(nf, cfs, cs, \
                            in_layer = encode_node_current)
                    if do_pool:
                        new_encode_node_current = net.pool(pfs, ps, \
                                in_layer = new_encode_node_current, pfunc = pool_type)
                    new_encode_nodes_current.append(new_encode_node_current)
                    #share the variables between current and future encoding
                    encode_scope.reuse_variables()
            
                #encode future images (conv + pool)
                new_encode_node_future = net.conv(nf, cfs, cs, \
                        in_layer = encode_nodes_future[i - 1])
                if do_pool:
                    new_encode_node_future = net.pool(pfs, ps, \
                            in_layer = new_encode_node_future, pfunc = pool_type)
 
                if(DEBUG):
                    print('Current encode node shape: ' + \
                            str(new_encode_node_current.get_shape().as_list()))
                    print('Future encode node shape: ' + \
                            str(new_encode_node_current.get_shape().as_list()))
                    print('Pool size %d, stride %d' % (pfs, ps))
                    print('Type: ' + pool_type) 

                #store layers
                encode_nodes_current.append(new_encode_nodes_current)
                encode_nodes_future.append(new_encode_node_future)


###### HIDDEN ######

        with tf.variable_scope('concat'):
            #flatten
            flat_node_current = tf.concat(3, encode_nodes_current[-1])
            flat_node_current = flatten(net, flat_node_current)
            flat_node_future = flatten(net, encode_nodes_future[-1])

            #concat current and future
            encode_flat = tf.concat(1, [flat_node_current, flat_node_future])

            #get hidden layer parameters
            nf0 = encode_flat.get_shape().as_list()[1]
            hidden_depth = gp.getHiddenDepth(rng, cfg, slippage=slippage)
  
            if(DEBUG):
                print('Hidden depth: %d' % hidden_depth)

        #fully connected hidden layers
        hidden = encode_flat
        for i in range(1, hidden_depth + 1):
            with tf.variable_scope('hidden' + str(i)):
                nf = gp.getHiddenNumFeatures(i, hidden_depth, rng, cfg, slippage=slippage)
                hidden = net.fc(nf, bias = 0.01, in_layer = hidden, dropout = None)
                nf0 = nf 
    
                if(DEBUG):
                    print('Hidden shape %s' % hidden.get_shape().as_list())

#        #TODO Test and remove summing actions
#        shape = actions_node.get_shape().as_list()
#        actions_node = net.reshape([6,int(shape[1]/6)], in_layer = actions_node)
#        actions_node = tf.reduce_sum(actions_node, 2)

        #match the shape of the action vector
        #by using another hidden layer if necessary
        ds = actions_node.get_shape().as_list()[1]

        if num_classes is not None:
            ds *= num_classes

        if ds != nf0:
            with tf.variable_scope('extra_hidden'):
                pred = net.fc(ds, bias = .01, activation = None, dropout = None)

            if(DEBUG):
                print("Linear from %d to %d" % (nf0, ds))
        else:
            pred = hidden

    if minmax_end:
        print("Min max clipping active")
        #pred = net.minmax(min_arg = 10, max_arg = -10, in_layer = pred)
        pred = tf.sigmoid(pred)
    #output batch normalized labels for storage and loss

    '''
    #first concatenate all actions into one batch batch to normalize across
    #the last two entries, i.e. the pixel values will always get normalized by 255
    norm_actions0 = []
    norm_actions1 = []
    for d in range(dim):
        norm_actions0.append(tf.slice(actions_node, [0, 8*d], [-1, 6]))
        norm_actions1.append(tf.slice(actions_node, [0, 6+8*d], [-1, 2]))
    norm_actions0 = tf.concat(0, norm_actions0)
    norm_actions1 = tf.concat(0, norm_actions1)

    #normalize
    epsilon = 1e-3
    batch_mean, batch_var = tf.nn.moments(norm_actions0, [0])
    norm_actions0 = (norm_actions0 - batch_mean) / tf.sqrt(batch_var + epsilon)
    norm_actions1 = norm_actions1 / 255.0

    #reassemble actions vector
    batch_size = pred.get_shape().as_list()[0]
    norm_actions = []
    for d in range(dim):
        norm_actions.append(tf.slice(norm_actions0, [d*batch_size, 0], [batch_size, -1]))
        norm_actions.append(tf.slice(norm_actions1, [d*batch_size, 0], [batch_size, -1]))
    norm_actions = tf.concat(1, norm_actions)
    # normalize action vector
    epsilon = 1e-3
    batch_mean, batch_var = tf.nn.moments(actions_node, [0])
    norm_actions = (actions_node - batch_mean) / tf.sqrt(batch_var + epsilon)
    ''' 

    outputs = {'pred': pred, 'norm_actions': actions_node, 
               'dim': dim, 'num_classes': num_classes}
    return outputs, net.params

def flatten(net, node):
    shape = node.get_shape().as_list()
    flat_node = net.reshape([np.prod(shape[1:])], in_layer = node)
    if(DEBUG):
        print('Flatten to shape %s' % flat_node.get_shape().as_list())
    return flat_node

def l2_action_loss(labels, logits, **kwargs):
    pred = logits['pred']
    shape = labels.get_shape().as_list()
    norm = shape[0] * shape[1]
    #batch normalized action features
    norm_labels = logits['norm_actions']
    #store normalized labels
    loss = tf.nn.l2_loss(pred - norm_labels) / norm    
    #loss = tf.minimum(loss, 0.1) #TODO remove and find reason!
    return loss

def binary_cross_entropy_action_loss(labels, logits, **kwargs):
    pred = logits['pred']
    dim = logits['dim']
    actions_node = logits['norm_actions']
    # Split action node and binary discretize
    action_shape = int(actions_node.get_shape().as_list()[1] / dim)
    actions_split = []
    for d in range(dim):
        act_sp = tf.slice(actions_node, [0, action_shape*d], [-1, action_shape])
#        act_sp = tf.reduce_sum(act_sp, 1)
        act_sp = tf.abs(act_sp)
        act_sp = tf.minimum(act_sp, 1)
        act_sp = tf.ceil(act_sp)        
#        act_sp = tf.reshape(act_sp, [-1, 1])
        actions_split.append(act_sp)
    norm_labels = tf.concat(1, actions_split)

    loss = -tf.reduce_sum(norm_labels * tf.log(pred) \
                          + (1 - norm_labels) * tf.log(1 - pred), 1)
    return loss

def softmax_cross_entropy_action_loss(labels, logits, **kwargs):
    pred = logits['pred']
    shape = labels.get_shape().as_list()
    norm_labels = logits['norm_actions']
    seq_len = logits['dim']
    dim = int(shape[1] / seq_len)

    '''
    #50:50 split
    pos_discount = np.array([10.13530233, 3.54033702, \
                             98.61325116, 2.72365054, \
                              1.92986523, 1.93214109])
    if dim == 4:
        pos_discount = pos_discount[0:4]

    rand = tf.random_uniform(shape)
    rands = []
    for i in range(seq_len):
        r = tf.slice(rand, [0, i*dim], [-1, dim])
        r = tf.multiply(r, pos_discount)
        r = tf.round(r)
        rands.append(r)
    rands = tf.concat(1, rands)
    rands = tf.cast(rands, tf.int32)
    '''

    #100:0 split, only consider pos examples
    rands = tf.ones(shape, dtype=tf.int32)

    # upper bound for our 5 buckets, the last upper bound is inf and hence
    # not necessary
    buckets_dim = logits['num_classes']
    if buckets_dim != 5:
        raise NotImplementedError('So far only num_classes=5 can be used \
              with this loss.')

    buckets = np.array(
              [[-5.0,  51.7, -156.1, -37.1, 141,  73], 
               [-4.9,  52.5,  -43.7,  -7.9, 178, 114], 
               [ 4.9,  52.6,   48.9,   7.5, 204, 140], 
               [ 5.1,  55.2,  166.7,  36.7, 230, 181]])
    if dim == 4:
        buckets = buckets[:,0:4]
    buckets = np.tile(buckets, (1,seq_len))

    # bucket labels
    labels = []
    new_shape = shape + [1]
    new_shape[0] = -1
    for i in range(buckets_dim):
        label = tf.zeros(shape, tf.bool)
        if i == 0:
            label = tf.less(norm_labels, buckets[i])
        elif i == buckets_dim - 1:
            label = tf.greater(norm_labels, buckets[i-1])
        else:
            label = tf.logical_and(tf.greater(norm_labels, buckets[i-1]), \
                                   tf.less(norm_labels, buckets[i]))
        label = tf.reshape(label, new_shape)
        labels.append(label)
    labels = tf.concat(2, labels)
    labels = tf.cast(labels, tf.int32)

    #find all positive indices
    zero = tf.constant(0, dtype=tf.float32)
    pos_idx = tf.not_equal(norm_labels, zero)
    neg_idx = tf.logical_not(pos_idx)        

    #mask out all negative entries
    rands = tf.reshape(rands, new_shape)
    pos_idx = tf.reshape(pos_idx, new_shape)
    neg_idx = tf.reshape(neg_idx, new_shape) 
    labels = labels * tf.cast(pos_idx, tf.int32) * rands \
           + labels * tf.cast(neg_idx, tf.int32) * (1-rands)

    pred = tf.reshape(pred, [-1,buckets_dim])
    #labels = tf.reshape(labels, [-1,5])
    loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(pred, labels))
    return loss

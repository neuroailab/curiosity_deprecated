'''
A modification of a basic asymmetric model that assumes that the hidden fc layers bring things forward one time step at a time.

Images_1 ... Images..._T_in -> Encoded data(T_in) -> Concat with action at time T_in -hidden forward step)> Encoded data(T_in + 1) -(hidden forward step)> Encoded data(T_in + 2)...

-> Then decode all of these


'''


"""
asymmetric model with bypass
"""
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function


import numpy as np
import tensorflow as tf
import zmq

from curiosity.models.model_building_blocks import ConvNetwithBypasses

ctx = zmq.Context()
sock = None
IMAGE_SIZE = None
NUM_CHANNELS = 3
ACTION_LENGTH = None

def initialize(host, port, datapath):
  global ctx, sock, IMAGE_SIZE, NUM_CHANNELS, ACTION_LENGTH
  sock = ctx.socket(zmq.REQ)
  print("connecting...")
  sock.connect("tcp://%s:%d" % (host, port))
  print("...connected")
  sock.send_json({'batch_size': 1,
                  'batch_num': 0,
                  'path': datapath,
                  'keys': [('randompermpairs2', 'images0'), 
                           ('randompermpairs2', 'actions')]
                 })
  images = recv_array(sock)
  actions = recv_array(sock)
  IMAGE_SIZE = images.shape[1]
  NUM_CHANNELS = images.shape[-1]
  ACTION_LENGTH = actions.shape[1]


def getEncodeDepth(rng, cfg, slippage=0):
  val = None
  if 'encode_depth' in cfg:
    val = cfg['encode_depth']
  elif 'encode' in cfg:
    val = max(cfg['encode'].keys())
  if val is not None and rng.uniform() > slippage:
    return val
  d = rng.choice([1, 2, 3, 4, 5])
  return d

def getEncodeConvFilterSize(i, encode_depth, rng, cfg, prev=None, slippage=0):
  val = None
  if 'encode' in cfg and (i in cfg['encode']):
    if 'conv' in cfg['encode'][i]:
      if 'filter_size' in cfg['encode'][i]['conv']:
        val = cfg['encode'][i]['conv']['filter_size']  
  if val is not None and rng.uniform() > slippage:
    return val
  L = [1, 3, 5, 7, 9, 11, 13, 15, 23]
  if prev is not None:
    L = [_l for _l in L if _l <= prev]
  return rng.choice(L)

def getEncodeConvNumFilters(i, encode_depth, rng, cfg, slippage=0):
  val = None
  if 'encode' in cfg and (i in cfg['encode']):
    if 'conv' in cfg['encode'][i]:
      if 'num_filters' in cfg['encode'][i]['conv']:
        val = cfg['encode'][i]['conv']['num_filters']
  if val is not None and rng.uniform() > slippage:
    return val
  L = [3, 48, 96, 128, 256, 128]
  return L[i]
  
def getEncodeConvStride(i, encode_depth, rng, cfg, slippage=0):
  val = None
  if 'encode' in cfg and (i in cfg['encode']):
    if 'conv' in cfg['encode'][i]:
      if 'stride' in cfg['encode'][i]['conv']:
        val = cfg['encode'][i]['conv']['stride']
  if val is not None and rng.uniform() > slippage:
    return val
  if encode_depth > 1:
    return 2 if i == 1 else 1
  else:
    return 3 if i == 1 else 1

def getEncodeDoPool(i, encode_depth, rng, cfg, slippage=0):
  val = None
  if 'encode' in cfg and (i in cfg['encode']):
    if 'do_pool' in cfg['encode'][i]:
      val = cfg['encode'][i]['do_pool']
    elif 'pool' in cfg['encode'][i]:
      val = True
  if val is not None and rng.uniform() > slippage:
    return val
  if i < 3 or i == encode_depth:
    return rng.uniform() < .75
  else:
    return rng.uniform() < .25
    
def getEncodePoolFilterSize(i, encode_depth, rng, cfg, slippage=0):
  val = None
  if 'encode' in cfg and (i in cfg['encode']):
    if 'pool' in cfg['encode'][i]:
      if 'filter_size' in cfg['encode'][i]['pool']:
        val = cfg['encode'][i]['pool']['filter_size']
  if val is not None and rng.uniform() > slippage:
    return val
  return rng.choice([2, 3, 4, 5])

def getEncodePoolStride(i, encode_depth, rng, cfg, slippage=0):  
  val = None
  if 'encode' in cfg and (i in cfg['encode']):
    if 'pool' in cfg['encode'][i]:
      if 'stride' in cfg['encode'][i]['pool']:
        val = cfg['encode'][i]['pool']['stride']
  if val is not None and rng.uniform() > slippage:
    return val
  return 2

def getEncodePoolType(i, encode_depth, rng, cfg, slippage=0):
  val = None
  if 'encode' in cfg and (i in cfg['encode']):
    if 'pool' in cfg['encode'][i]:
      if 'type' in cfg['encode'][i]['pool']:
        val = cfg['encode'][i]['pool']['type']
  if val is not None and rng.uniform() > slippage:
    return val
  return rng.choice(['max', 'avg'])

def getHiddenDepth(rng, cfg, slippage=0):
  val = None
  if (not rng.uniform() < slippage) and 'hidden_depth' in cfg:
    val = cfg['hidden_depth']
  elif 'hidden' in cfg:
    val = max(cfg['hidden'].keys())
  if val is not None and rng.uniform() > slippage:
    return val
  d = rng.choice([1, 2, 3])
  return d

def getHiddenNumFeatures(i, hidden_depth, rng, cfg, slippage=0):
  val = None
  if 'hidden' in cfg and (i in cfg['hidden']):
    if 'num_features' in cfg['hidden'][i]:
      val = cfg['hidden'][i]['num_features']
  if val is not None and rng.uniform() > slippage:
    return val
  return 1024

def getDecodeDepth(rng, cfg, slippage=0):
  val = None
  if 'decode_depth' in cfg:
    val = cfg['decode_depth']
  elif 'decode' in cfg:
    val = max(cfg['decode'].keys())
  if val is not None and rng.uniform() > slippage:
    return val
  d = rng.choice([1, 2, 3])
  return d

def getDecodeNumFilters(i, decode_depth, rng, cfg, slippage=0):
  if i < decode_depth:
    val = None
    if 'decode' in cfg and (i in cfg['decode']):
      if 'num_filters' in cfg['decode'][i]:
        val = cfg['decode'][i]['num_filters']
    if val is not None and rng.uniform() > slippage:
      return val
    return 32
  else:
    return NUM_CHANNELS

def getDecodeFilterSize(i, decode_depth, rng, cfg, slippage=0):
  val = None
  if 'decode' in cfg and (i in cfg['decode']):
     if 'filter_size' in cfg['decode'][i]:
       val = cfg['decode'][i]['filter_size']
  if val is not None and rng.uniform() > slippage:
    return val
  return rng.choice([1, 3, 5, 7, 9, 11])

def getDecodeSize(i, decode_depth, init, final, rng, cfg, slippage=0):
  val = None
  if 'decode' in cfg and (i in cfg['decode']):
    if 'size' in cfg['decode'][i]:
      val = cfg['decode'][i]['size']
  if val is not None and rng.uniform() > slippage:
    return val
  s = np.log2(init)
  e = np.log2(final)
  increment = (e - s) / decode_depth
  l = np.around(np.power(2, np.arange(s, e, increment)))
  if len(l) < decode_depth + 1:
    l = np.concatenate([l, [final]])
  l = l.astype(np.int)
  return l[i]

def getDecodeBypass(i, encode_nodes, decode_size, decode_depth, rng, cfg, slippage=0):
  val = None
  if 'decode' in cfg and (i in cfg['decode']):
    if 'bypass' in cfg['decode'][i]:
      val = cfg['decode'][i]['bypass']
  #prevent error that can occur here if encode is not large enough due to slippage modification?
  if val is not None and rng.uniform() > slippage:
    return val 
  switch = rng.uniform() 
  print('sw', switch)
  if switch < 0.5:
    sdiffs = [e.get_shape().as_list()[1] - decode_size for e in encode_nodes]
    return np.abs(sdiffs).argmin()
    
def getFilterSeed(rng, cfg):
  if 'filter_seed' in cfg:
    return cfg['filter_seed']
  else:  
    return rng.randint(10000)
  

def model(data, actions_node, time_node, rng, cfg, slippage=0, slippage_error=False):
  """The Model definition."""
  cfg0 = {} 

  fseed = getFilterSeed(rng, cfg)
  
  #encoding
  nf0 = NUM_CHANNELS
  imsize = IMAGE_SIZE
  encode_depth = getEncodeDepth(rng, cfg, slippage=slippage)
  cfg0['encode_depth'] = encode_depth
  print('Encode depth: %d' % encode_depth)
  encode_nodes = []
  encode_nodes.append(data)
  cfs0 = None
  cfg0['encode'] = {}
  for i in range(1, encode_depth + 1):
    cfg0['encode'][i] = {}
    cfs = getEncodeConvFilterSize(i, encode_depth, rng, cfg, prev=cfs0, slippage=slippage)
    cfg0['encode'][i]['conv'] = {'filter_size': cfs}
    cfs0 = cfs
    nf = getEncodeConvNumFilters(i, encode_depth, rng, cfg, slippage=slippage)
    cfg0['encode'][i]['conv']['num_filters'] = nf
    cs = getEncodeConvStride(i, encode_depth, rng, cfg, slippage=slippage)
    cfg0['encode'][i]['conv']['stride'] = cs
    W = tf.Variable(tf.truncated_normal([cfs, cfs, nf0, nf],
                                        stddev=0.01,
                                        seed=fseed))
    new_encode_node = tf.nn.conv2d(encode_nodes[i-1], W,
                               strides = [1, cs, cs, 1],
                               padding='SAME')
    new_encode_node = tf.nn.relu(new_encode_node)
    b = tf.Variable(tf.zeros([nf]))
    new_encode_node = tf.nn.bias_add(new_encode_node, b)
    imsize = imsize // cs
    print('Encode conv %d with size %d stride %d num channels %d numfilters %d for shape' % (i, cfs, cs, nf0, nf), new_encode_node.get_shape().as_list())    
    do_pool = getEncodeDoPool(i, encode_depth, rng, cfg, slippage=slippage)
    if do_pool:
      pfs = getEncodePoolFilterSize(i, encode_depth, rng, cfg, slippage=slippage)
      cfg0['encode'][i]['pool'] = {'filter_size': pfs}
      ps = getEncodePoolStride(i, encode_depth, rng, cfg, slippage=slippage)
      cfg0['encode'][i]['pool']['stride'] = ps
      pool_type = getEncodePoolType(i, encode_depth, rng, cfg, slippage=slippage)
      cfg0['encode'][i]['pool']['type'] = pool_type
      if pool_type == 'max':
        pfunc = tf.nn.max_pool
      elif pool_type == 'avg':
        pfunc = tf.nn.avg_pool
      new_encode_node = pfunc(new_encode_node,
                          ksize = [1, pfs, pfs, 1],
                          strides = [1, ps, ps, 1],
                          padding='SAME')
      print('Encode %s pool %d with size %d stride %d for shape' % (pool_type, i, pfs, ps),
                    new_encode_node.get_shape().as_list())
      imsize = imsize // ps
    nf0 = nf

    encode_nodes.append(new_encode_node)   

  encode_node = encode_nodes[-1]
  enc_shape = encode_node.get_shape().as_list()
  encode_flat = tf.reshape(encode_node, [enc_shape[0], np.prod(enc_shape[1:])])
  print('Flatten to shape %s' % encode_flat.get_shape().as_list())

  encode_flat = tf.concat(1, [encode_flat, actions_node, time_node]) 
  #hidden
  nf0 = encode_flat.get_shape().as_list()[1]
  hidden_depth = getHiddenDepth(rng, cfg, slippage=slippage)
  cfg0['hidden_depth'] = hidden_depth
  hidden = encode_flat
  cfg0['hidden'] = {}
  for i in range(1, hidden_depth + 1):
    nf = getHiddenNumFeatures(i, hidden_depth, rng, cfg, slippage=slippage)
    cfg0['hidden'][i] = {'num_features': nf}
    W = tf.Variable(tf.truncated_normal([nf0, nf],
                                        stddev = 0.01,
                                        seed=fseed))    
    b = tf.Variable(tf.constant(0.01, shape=[nf]))
    hidden = tf.nn.relu(tf.matmul(hidden, W) + b)
    print('hidden layer %d %s' % (i, str(hidden.get_shape().as_list())))
    nf0 = nf

  #decode
  decode_depth = getDecodeDepth(rng, cfg, slippage=slippage)
  cfg0['decode_depth'] = decode_depth
  print('Decode depth: %d' % decode_depth)
  nf = getDecodeNumFilters(0, decode_depth, rng, cfg, slippage=slippage)
  cfg0['decode'] = {0: {'num_filters': nf}}
  ds = getDecodeSize(0, decode_depth, enc_shape[1], IMAGE_SIZE, rng, cfg, slippage=slippage)
  cfg0['decode'][0]['size'] = ds
  if ds * ds * nf != nf0:
    W = tf.Variable(tf.truncated_normal([nf0, ds * ds * nf],
                                        stddev = 0.01,
                                        seed=fseed))
    b = tf.Variable(tf.constant(0.01, shape=[ds * ds * nf]))
    hidden = tf.matmul(hidden, W) + b
    print("Linear from %d to %d for input size %d" % (nf0, ds * ds * nf, ds))
  decode = tf.reshape(hidden, [enc_shape[0], ds, ds, nf])  
  print("Unflattening to", decode.get_shape().as_list())
  for i in range(1, decode_depth + 1):
    nf0 = nf
    ds = getDecodeSize(i, decode_depth, enc_shape[1], IMAGE_SIZE, rng, cfg, slippage=slippage)
    cfg0['decode'][i] = {'size': ds}
    if i == decode_depth:
       assert ds == IMAGE_SIZE, (ds, IMAGE_SIZE)
    decode = tf.image.resize_images(decode, ds, ds)
    print('Decode resize %d to shape' % i, decode.get_shape().as_list())
    add_bypass = getDecodeBypass(i, encode_nodes, ds, decode_depth, rng, cfg, slippage=slippage)
    if add_bypass != None:
      bypass_layer = encode_nodes[add_bypass]
      bypass_shape = bypass_layer.get_shape().as_list()
      if bypass_shape[1] != ds:
        bypass_layer = tf.image.resize_images(bypass_layer, ds, ds)
      decode = tf.concat(3, [decode, bypass_layer])
      print('Decode bypass from %d at %d for shape' % (add_bypass, i), decode.get_shape().as_list())
      nf0 = nf0 + bypass_shape[-1]
      cfg0['decode'][i]['bypass'] = add_bypass
    cfs = getDecodeFilterSize(i, decode_depth, rng, cfg, slippage=slippage)
    cfg0['decode'][i]['filter_size'] = cfs
    nf = getDecodeNumFilters(i, decode_depth, rng, cfg, slippage=slippage)
    cfg0['decode'][i]['num_filters'] = nf
    if i == decode_depth:
      assert nf == NUM_CHANNELS, (nf, NUM_CHANNELS)
    W = tf.Variable(tf.truncated_normal([cfs, cfs, nf0, nf],
                                        stddev=0.1,
                                        seed=fseed))
    b = tf.Variable(tf.zeros([nf]))
    decode = tf.nn.conv2d(decode,
                          W,
                          strides=[1, 1, 1, 1],
                          padding='SAME')
    decode = tf.nn.bias_add(decode, b)
    print('Decode conv %d with size %d num channels %d numfilters %d for shape' % (i, cfs, nf0, nf), decode.get_shape().as_list())

    if i < decode_depth: 
      decode = tf.nn.relu(decode)
    else:
      decode = tf.minimum(tf.maximum(decode, -1), 1)

  return decode, cfg0


def model_tfutils_fpd_compatible(inputs, **kwargs):
  batch_size = inputs['images'].get_shape().as_list()[0]
  new_inputs = {'images' : inputs['images'], 'actions' : inputs['parsed_actions'], 'time' : tf.ones([batch_size, 1])}
  return model_tfutils(new_inputs, **kwargs)


def model_tfutils(inputs, rng, cfg = {}, train = True, slippage = 0, T_in = 1, T_out = 1, num_channels = 3, action_size = 25, **kwargs):
  '''Model definition, compatible with tfutils.

  inputs should have 'current', 'future', 'action', 'time' keys. Outputs is a dict with keys, pred and future, within those, dicts with keys predi and futurei for i in 0:encode_depth, to be matched up in loss.'''
  # image_sequence = tf.divide(tf.cast(inputs['images'], tf.float32), 255.)
  actions_sequence = tf.cast(inputs['actions'], tf.float32)

  current_node = inputs['images'][:, :, :, :num_channels * T_in]
  current_node = tf.divide(tf.cast(current_node, tf.float32), 255.)
  future_node = inputs['images'][:, :, :, num_channels * T_in : ]
  assert num_channels * (T_in + T_out) == inputs['images'].get_shape().as_list()[3]

  # current_node = inputs['images'][]
  # current_node = inputs['current']
  # actions_node = inputs['actions']
  time_node = inputs['time']



  # current_node = tf.divide(tf.cast(current_node, tf.float32), 255.)
  # actions_node = tf.cast(actions_node, tf.float32)



  image_size = current_node.get_shape().as_list()[1]
  # num_channels = current_node.get_shape().as_list()[3]

#I think this should be taken away from cfg
  # fseed = getFilterSeed(rng, cfg)

  if rng is None:
    rng = np.random.RandomState(seed=kwargs['seed'])

  m = ConvNetwithBypasses(**kwargs)
  m.output = current_node
  encode_nodes = [current_node]
  #encoding
  encode_depth = getEncodeDepth(rng, cfg, slippage=slippage)
  print('Encode depth: %d' % encode_depth)
  cfs0 = None

  for i in range(1, encode_depth + 1):
    #not sure this usage ConvNet class creates exactly the params that we want to have, specifically in the 'input' field, but should give us an accurate record of this network's configuration
    with tf.variable_scope('encode' + str(i)):

      with tf.contrib.framework.arg_scope([m.conv], init='trunc_norm', stddev=.01, bias=0, activation='relu'):

        cfs = getEncodeConvFilterSize(i, encode_depth, rng, cfg, prev=cfs0, slippage=slippage)
        cfs0 = cfs
        nf = getEncodeConvNumFilters(i, encode_depth, rng, cfg, slippage=slippage)
        cs = getEncodeConvStride(i, encode_depth, rng, cfg, slippage=slippage)

        m.conv(nf, cfs, cs)
  #TODO add print function
      do_pool = getEncodeDoPool(i, encode_depth, rng, cfg, slippage=slippage)
      if do_pool:
        pfs = getEncodePoolFilterSize(i, encode_depth, rng, cfg, slippage=slippage)
        ps = getEncodePoolStride(i, encode_depth, rng, cfg, slippage=slippage)
        pool_type = getEncodePoolType(i, encode_depth, rng, cfg, slippage=slippage)
        m.pool(pfs, ps)
      encode_nodes.append(m.output)

  hidden_depth = getHiddenDepth(rng, cfg, slippage=slippage)
  print('Hidden depth: %d' % hidden_depth)
  encoded_states = []

  #forward one time step
  with tf.variable_scope('flatten'):
  	enc_shape = m.output.get_shape().as_list()
  	current_encoded_state = m.reshape([np.prod(enc_shape[1:])])
  for t in range(1, T_out + 1):
  	with tf.variable_scope('addaction'):
  		next_action = actions_node[(T_in + t - 1) * action_size : (T_in + t) * action_size]
  		m.add_bypass(next_action)
  	nf0 = m.output.get_shape().as_list()[1]
  	for i in range(1, hidden_depth + 1):
  		with tf.variable_scope('hidden' + str(i)) as scope:
  			if t > 1:
  				scope.reuse_variables()
  			nf = getHiddenNumFeatures(i, hidden_depth, rng, cfg, slippage=slippage)
  			m.fc(nf, init = 'trunc_norm', activation = 'relu', bias = .01, dropout = None)
  			nf0 = nf
  	encoded_states.append(m.output)
  	assert m.output.get_shape().as_list() == current_encoded_state.get_shape().as_list()
  	#this naming of things isn't super functional
  	current_encoded_state = m.output

  decode_depth = getDecodeDepth(rng, cfg, slippage=slippage)

  decoded = []

  for t in range(1, T_out + 1):
  	m.output = encoded_states[t - 1]
  	ds = getDecodeSize(0, decode_depth, enc_shape[1], IMAGE_SIZE, rng, cfg, slippage=slippage)
  	nf1 = getDecodeNumFilters(0, encode_depth, rng, cfg, slippage=slippage)
	  if ds * ds * nf1 != nf0:
	    with tf.variable_scope('extra_hidden') as scope:
	    	if t > 1:
	    		scope.reuse_variables()
	     	m.fc(ds * ds * nf1, init = 'trunc_norm', activation  = None, bias = .01, dropout = None)
	    print("Linear from %d to %d for input size %d" % (nf0, ds * ds * nf1, ds))
	  m.reshape([ds, ds, nf1])
	  print("Unflattening to", m.output.get_shape().as_list())
    for i in range(1, decode_depth + 1):
      with tf.variable_scope('decode' + str(i+1)) as scope:
      	if t > 1:
      		scope.reuse_variables()
        ds = getDecodeSize(i, decode_depth, enc_shape[1], image_size, rng, cfg, slippage=slippage)
        if i == decode_depth:
          assert ds == image_size, (ds, image_size)
        m.resize_images(ds)
        print('Decode resize %d to shape' % i, m.output.get_shape().as_list())
        add_bypass = getDecodeBypass(i, encode_nodes, ds, decode_depth, rng, cfg, slippage=slippage)
        if add_bypass != None:
          bypass_layer = encode_nodes[add_bypass]
          bypass_shape = bypass_layer.get_shape().as_list()
          # if bypass_shape[1] != ds:
          #   bypass_layer = tf.image.resize_images(bypass_layer, ds, ds)
          m.add_bypass(bypass_layer)
          print('Decode bypass from %d at %d for shape' % (add_bypass, i), m.output.get_shape().as_list())

        cfs = getDecodeFilterSize(i, encode_depth, rng, cfg, slippage=slippage)
        nf1 = getDecodeNumFilters(i, encode_depth, rng, cfg, slippage=slippage)
        #hack, some sort of cfg processing problem?
        if nf1 is None:
          nf1 = cfg['decode'][i]['num_filters']
        if i == decode_depth:
          assert nf1 == num_channels
          m.conv(nf1, cfs, 1, init = 'trunc_norm', stddev = .1, bias = 0, activation = None)
        # m.minmax(min_arg = 1, max_arg = -1)
        else:
          m.conv(nf1, cfs, 1, init='trunc_norm', stddev=.1, bias=0, activation='relu')
    decoded.append(m.output)

  pred = tf.concat(decoded, 3)

  return {'pred' : pred, 'tv' : future_node}, m.params

def compute_diffs_timestep_1(original_image, subsequent_images, num_channels = 3):
  curr_image = original_image
  diffs = []
  for i in range(int(subsequent_images.get_shape().as_list()[-1] / num_channels)):
    next_image = subsequent_images[:, :, :, num_channels * i : num_channels * (i + 1)]
    diffs.append(next_image - curr_image)
    curr_image = next_image
  return tf.concat(3, diffs)

def something_or_nothing_loss_fn(outputs, image, threshold = None, num_channels = 3, **kwargs):
  print('inside loss')
  print(outputs)
  print(image)
  pred = outputs['pred']
  future_images = tf.cast(outputs['tv'], 'float32')
  assert threshold is not None
  T_in = int((image.get_shape().as_list()[-1] -  pred.get_shape().as_list()[-1]) / num_channels)
  original_image = image[:, :, :, (T_in - 1) * num_channels: T_in * num_channels]
  original_image = tf.cast(original_image, 'float32')
  diffs = compute_diffs_timestep_1(original_image, future_images, num_channels = num_channels)
  #just measure some absolute change relative to a threshold
  diffs = tf.abs(diffs / 255.) - threshold
  tv = tf.cast(tf.ceil(diffs), 'uint8')
  tv = tf.one_hot(tv, depth = 2)
  my_shape = pred.get_shape().as_list()
  my_shape.append(1)
  pred = tf.reshape(pred, my_shape)
  pred = tf.concat(4, [tf.zeros(my_shape), pred])
  return tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(pred, tv))






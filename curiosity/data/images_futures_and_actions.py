from tfutils.data import HDF5DataProvider
import numpy as np
import json

class FuturePredictionData(HDF5DataProvider):
    def __init__(self,
		 data_path,
		 batch_size=1,
		 crop_size=None,
		 min_time_difference=1, # including, also specifies fixed time
		 max_time_difference=2, # excluding
		 random_time=False,
		 *args,
		 **kwargs):
	"""
	A specific reader for ThreeDWorld data stored as a HDF5 file.
	The data will be parsed into an image and action at time t as input 
	and an image and action at time t+1 as output.

	Note: 	
	    This data provider should be used with RandomShuffleQueue since the 
	    data in the HDF5 file is not expected to be shuffled ahead of time.

	Args:
	    - data_path
	        path to ThreeDWorld data

        Kwargs: 
	    - batch_size (int, default: 1)
	        Number of images to return when `next` is called. By default set
	        to 1 since it is expected to be used with queues where reading one
	        image at a time is ok.
   	    - crop_size (int or None, default: None)
	        For center crop (crop_size x crop_size). If None, no cropping will occur.
	    - *args, **kwargs
	        Extra arguments for HDF5DataProvider
        """	    
    
        images = 'images'
        actions = 'actions'
        future_images = 'future_images'
        future_actions = 'future_actions'
        super(FuturePredictionData, self).__init__(
	    data_path,
	    [images, actions],
	    batch_size=batch_size,
	    postprocess={images: self.postproc_img, actions: self.postproc_actions},
	    pad=False,
	    *args, **kwargs)

        if crop_size is None:
	    self.crop_size = 256
        else:
	    self.crop_size = crop_size

        self.random_time = random_time
    
        if int(min_time_difference) < 1:
   	    self.min_time_difference = 1
	    print("The minimum time difference has to be at least 1, " \
	        + "and thus was set to 1.") 
        else:
	    self.min_time_difference = int(min_time_difference)

        if int(max_time_difference) < self.min_time_difference:
	    self.max_time_difference = self.min_time_difference + 1
	    print("The maximum time difference has to be bigger than, " \
	        + "the minimum time difference and thus was set to %d." \
	        % self.max_time_difference)
        else:
	    self.max_time_difference = int(max_time_difference)

        self.random_time = random_time

    def postproc_img(self, ims, f):
	# normalization and random cropping
	norm = ims.astype(np.float32) / 255
	off = np.random.randint(0, 256 - self.crop_size, size=2)
	images_batch = norm[:,
                            off[0]: off[0] + self.crop_size,
                            off[1]: off[1] + self.crop_size]
	return images_batch

    def postproc_actions(self, actions, f):
	# parse actions into vector 
	parsed_actions = []
	for action in actions:
	    action = json.loads(action)
	    # parsed action vector
	    pact = []
	    # pact[0] : teleport random
	    if 'teleport_random' in action and action['teleport_random'] is True:
		pact.append(1)
	    else:
		pact.append(0)
	    # pact[1:4] : agent velocity
	    if 'vel' in action:
		pact.extend(action['vel'])
	    else:
		pact.extend(np.zeros(3))
	    # pact[4:7] : agent angular velocity
	    if 'ang_vel' in action:
                pact.extend(action['ang_vel'])
            else: 
		pact.extend(np.zeros(3))
	    # pact[7:25] : actions
	    if 'actions' in action:
		# fill object actions vector
		object_actions = []
		for objact in action['actions']:
		    if 'force' in objact:
			object_actions.extend(objact['force'])
		    else:
			object_actions.extend(np.zeros(3))
		    if 'torque' in objact:
			object_actions.extend(objact['torque'])
		    else:
			object_actions.extend(np.zeros(3))
		    """
			The chosen object not necessarily the one acted upon
			depending on action_pos. The actual object acted upon
			is stored in 'id'
		    """
		    if 'object' in objact:
			object_actions.append(int(objact['object']))
		    else:
			object_actions.append(0)
		    if 'action_pos' in objact:
			object_actions.extend(objact['action_pos'])
		    else:
			object_actions.extend(np.zeros(2))
		""" 
			Each object action vector has a length of 3+3+1+2=9.
			Object actions are performed on maximally 2 objects
			simultanously (CRASHING action). Thus, the vector length
			has to be 2*9=18
		"""
		while len(object_actions) < 18:
		    object_actions.append(0)
		# append object actions vector
		pact.extend(object_actions)
	    parsed_actions.append(pact)
	return np.array(parsed_actions)

    def next(self):
	batch = super(FuturePredictionData, self).next()
	# create present-future image/action pairs
	img, act, fut_img, fut_act = self.create_image_pairs(batch[images], batch[actions])
	feed_dict = {images: np.squeeze(img),
		     actions: np.squeeze(act),
		     future_images: np.squeeze(fut_img),
		     future_actions: np.squeeze(fut_act)}
	return feed_dict

    def create_image_pairs(self, input_images, input_actions):
	"""
	    create present-future image/action pairs with either
		- fixed time differences or 
		- variable time differences 
	    between the image pairs as specified by the user
	"""	
	images = []
	actions = []
	future_images = []
	future_actions = []
	if len(input_images) < 1 or len(input_actions) < 1:
	    return [images, actions, future_images, future_actions]
	# specify the length of the action sequence based on the maximally possible delta_t
	delta_t = self.min_time_difference
	if self.random_time:
	    delta_t = self.max_time_difference
	action_sequence_length = delta_t * len(input_actions[0])
	image_sequence_length = delta_t * input_images[0].shape[2] 
	# create present-future image/action pairs
	for i in range(len(input_images)):	    
	    # select time delta
	    if self.random_time:
		max_time_difference = min(len(input_images) - i, self.max_time_difference)
		if max_time_difference <= self.min_time_difference \
			or max_time_difference < 1:
		    continue
		delta_t = np.random.randint(self.min_time_difference, max_time_difference)
	    # create image sequence and pad if necessary
	    image_sequence = np.concatenate(input_images[i:i+delta_t], axis=2)
	    while image_sequence.shape[2] < image_sequence_length:
		image_sequence = np.concatenate((image_sequence, \
			np.zeros(input_images[0].shape)), axis=2)
	    # create action sequence and pad if necessary 
	    action_sequence = np.concatenate(input_actions[i:i+delta_t], axis=0)
	    while len(action_sequence) < action_sequence_length:
		action_sequence = np.concatenate(action_sequence, \
			np.zeros(len(input_actions[0])), axis=0)
	    # append present-future image/action pair
	    images.append(image_sequence)
	    actions.append(action_sequence)
	    future_images.append(input_images[i+delta_t])
	    future_actions.append(input_actions[i+delta_t])
	return [images, actions, future_images, future_actions]
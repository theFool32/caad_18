"""Implementation of sample defense.

This defense loads inception resnet v2 checkpoint and classifies all images
using loaded checkpoint.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os

import numpy as np
import tensorflow as tf
from scipy.misc import imread

from nets import inception_resnet_v2

slim = tf.contrib.slim

tf.flags.DEFINE_string(
    'master', '', 'The address of the TensorFlow master to use.')

tf.flags.DEFINE_string(
    'checkpoint_path', '', 'Path to checkpoint for inception network.')

tf.flags.DEFINE_string(
    'input_dir', '', 'Input directory with images.')

tf.flags.DEFINE_string(
    'output_file', '', 'Output file to save labels.')

tf.flags.DEFINE_integer(
    'image_width', 299, 'Width of each input images.')

tf.flags.DEFINE_integer(
    'image_height', 299, 'Height of each input images.')

tf.flags.DEFINE_integer(
    'batch_size', 16, 'How many images process at one time.')

tf.flags.DEFINE_float(
    'max_epsilon', 16.0, 'Maximum size of adversarial perturbation.')

FLAGS = tf.flags.FLAGS


def load_images(input_dir, batch_shape):
    """Read png images from input directory in batches.

    Args:
      input_dir: input directory
      batch_shape: shape of minibatch array, i.e. [batch_size, height, width, 3]

    Yields:
      filenames: list file names without path of each image
        Lenght of this list could be less than batch_size, in this case only
        first few images of the result are elements of the minibatch.
      images: array with all images from this batch
    """
    images = np.zeros(batch_shape)
    filenames = []
    idx = 0
    batch_size = batch_shape[0]
    for filepath in tf.gfile.Glob(os.path.join(input_dir, '*.png')):
        with tf.gfile.Open(filepath, 'rb') as f:
            # image = imread(f, mode='RGB').astype(np.float) / 255.0
            image0 = imread(f, mode='RGB')
            image1 = (image0 // 64) * 64 + 32
            image = image1.astype(np.float) / 255.0

        # Images for inception classifier are normalized to be in [-1, 1] interval.
        images[idx, :, :, :] = image * 2.0 - 1.0
        filenames.append(os.path.basename(filepath))
        idx += 1
        if idx == batch_size:
            yield filenames, images
            filenames = []
            images = np.zeros(batch_shape)
            idx = 0
    if idx > 0:
        yield filenames, images


def main(_):
    # eps = FLAGS.max_epsilon / 255.0
    eps = 2.0 / 255.0

    batch_shape = [FLAGS.batch_size, FLAGS.image_height, FLAGS.image_width, 3]
    num_classes = 1001

    tf.logging.set_verbosity(tf.logging.INFO)

    origin_preds = {}
    flip_preds = {}
    all_filenames = []

    # Origin
    with tf.Graph().as_default():
        # Prepare graph
        # x_input is a binary image (converted in the load_images phase)
        x_input = tf.placeholder(tf.float32, shape=batch_shape)

        with slim.arg_scope(inception_resnet_v2.inception_resnet_v2_arg_scope()):
            _, end_points = inception_resnet_v2.inception_resnet_v2(
                x_input, num_classes=num_classes, is_training=False)

        predictions = end_points['Predictions']

        # Run computation
        saver = tf.train.Saver(slim.get_model_variables())
        session_creator = tf.train.ChiefSessionCreator(
            scaffold=tf.train.Scaffold(saver=saver),
            checkpoint_filename_with_path=FLAGS.checkpoint_path,
            master=FLAGS.master)

        with tf.train.MonitoredSession(session_creator=session_creator) as sess:
            with tf.gfile.Open(FLAGS.output_file, 'w') as out_file:
                for filenames, images in load_images(FLAGS.input_dir, batch_shape):
                    pred = sess.run(predictions, feed_dict={x_input: images})
                    for filename, p in zip(filenames, list(pred)):
                        origin_preds[filename] = p

                        # Keep the filename as well
                        all_filenames.append(filename)


    # Flip
    # tf.reset_default_graph()
    with tf.Graph().as_default():
        # Prepare graph
        # x_input is a binary image (converted in the load_images phase)
        x_input = tf.placeholder(tf.float32, shape=batch_shape)

        x_input_flip = tf.image.flip_left_right(x_input)

        with slim.arg_scope(inception_resnet_v2.inception_resnet_v2_arg_scope()):
            _, end_points = inception_resnet_v2.inception_resnet_v2(
                x_input_flip, num_classes=num_classes, is_training=False)

        predictions = end_points['Predictions']

        # Run computation
        saver = tf.train.Saver(slim.get_model_variables())
        session_creator = tf.train.ChiefSessionCreator(
            scaffold=tf.train.Scaffold(saver=saver),
            checkpoint_filename_with_path=FLAGS.checkpoint_path,
            master=FLAGS.master)

        with tf.train.MonitoredSession(session_creator=session_creator) as sess:
            with tf.gfile.Open(FLAGS.output_file, 'w') as out_file:
                for filenames, images in load_images(FLAGS.input_dir, batch_shape):
                    pred = sess.run(predictions, feed_dict={x_input: images})
                    for filename, p in zip(filenames, list(pred)):
                        flip_preds[filename] = p

    # Merge
    for filename in all_filenames:
        p = (origin_preds[filename] + flip_preds[filename]) / 2
        p_str = " ".join([str(i) for i in list(p)])
        out_file.write('{0},{1}\n'.format(filename, p_str))

if __name__ == '__main__':
    tf.app.run()

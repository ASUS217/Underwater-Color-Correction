'''

   Main training file

   The goal is to correct the colors in underwater images.
   CycleGAN was used to create images that appear to be underwater.
   Those will be sent into the generator, which will attempt to correct the
   colors.

'''

import cPickle as pickle
import tensorflow as tf
from scipy import misc
import numpy as np
import argparse
import ntpath
import pix2pix
import sys
import os
import time
import glob

sys.path.insert(0, 'ops/')
from tf_ops import *

import data_ops

if __name__ == '__main__':
   parser = argparse.ArgumentParser()
   parser.add_argument('--DATA',          required=False,default='rocks',type=str,help='Dataset to use')
   parser.add_argument('--EPOCHS',        required=False,default=4,type=int,help='Number of epochs for GAN')
   parser.add_argument('--NETWORK',       required=False,default='pix2pix',type=str,help='Network to use')
   parser.add_argument('--L1_WEIGHT',     required=False,default=100,type=int,help='Weight term for L1 loss')
   parser.add_argument('--BATCH_SIZE',    required=False,default=32,type=int,help='Batch size')
   parser.add_argument('--LOSS_METHOD',   required=False,default='gan',help='Loss function for GAN')
   parser.add_argument('--LEARNING_RATE', required=False,default=2e-5,type=float,help='Learning rate')
   a = parser.parse_args()

   LEARNING_RATE = a.LEARNING_RATE
   LOSS_METHOD   = a.LOSS_METHOD
   BATCH_SIZE    = a.BATCH_SIZE
   L1_WEIGHT     = a.L1_WEIGHT
   NETWORK       = a.NETWORK
   EPOCHS        = a.EPOCHS
   DATA          = a.DATA

   EXPERIMENT_DIR = 'checkpoints/LOSS_METHOD_'+LOSS_METHOD\
                     +'/NETWORK_'+NETWORK\
                     +'/L1_WEIGHT_'+str(L1_WEIGHT)\
                     +'/DATA_'+DATA+'/'\

   IMAGES_DIR     = EXPERIMENT_DIR+'images/'

   print
   print 'Creating',EXPERIMENT_DIR
   try: os.makedirs(IMAGES_DIR)
   except: pass
   
   # write all this info to a pickle file in the experiments directory
   exp_info = dict()
   exp_info['LEARNING_RATE'] = LEARNING_RATE
   exp_info['LOSS_METHOD']   = LOSS_METHOD
   exp_info['BATCH_SIZE']    = BATCH_SIZE
   exp_info['L1_WEIGHT']     = L1_WEIGHT
   exp_info['NETWORK']       = NETWORK
   exp_info['EPOCHS']        = EPOCHS
   exp_info['DATA']          = DATA
   exp_pkl = open(EXPERIMENT_DIR+'info.pkl', 'wb')
   data = pickle.dumps(exp_info)
   exp_pkl.write(data)
   exp_pkl.close()
   
   print
   print 'LEARNING_RATE: ',LEARNING_RATE
   print 'LOSS_METHOD:   ',LOSS_METHOD
   print 'BATCH_SIZE:    ',BATCH_SIZE
   print 'NETWORK:       ',NETWORK
   print 'EPOCHS:        ',EPOCHS
   print

   if NETWORK == 'pix2pix': from pix2pix import *

   # global step that is saved with a model to keep track of how many steps/epochs
   global_step = tf.Variable(0, name='global_step', trainable=False)

   # underwater image
   image_u = tf.placeholder(tf.float32, shape=(BATCH_SIZE, 256, 256, 3), name='image_u')

   # correct image
   image_r = tf.placeholder(tf.float32, shape=(BATCH_SIZE, 256, 256, 3), name='image_r')

   # generated corrected colors
   gen_image = netG(image_u)

   # send 'above' water images to D
   D_real = pix2pix.netD(image_r)

   # send corrected underwater images to D
   D_fake = pix2pix.netD(gen_image, reuse=True)

   e = 1e-12
   if LOSS_METHOD == 'least_squares':
      print 'Using least squares loss'
      errD_real = tf.nn.sigmoid(D_real)
      errD_fake = tf.nn.sigmoid(D_fake)
      errG = 0.5*(tf.reduce_mean(tf.square(errD_fake - 1)))
      errD = tf.reduce_mean(0.5*(tf.square(errD_real - 1)) + 0.5*(tf.square(errD_fake)))
   if LOSS_METHOD == 'gan':
      print 'Using original GAN loss'
      D_real = tf.nn.sigmoid(D_real)
      D_fake = tf.nn.sigmoid(D_fake)
      errG = tf.reduce_mean(-tf.log(D_fake + e))
      errD = tf.reduce_mean(-(tf.log(D_real+e)+tf.log(1-D_fake+e)))

   if L1_WEIGHT > 0.0:
      l1_loss = tf.reduce_mean(tf.abs(gen_image-image_r))
      errG += L1_WEIGHT*l1_loss

   # tensorboard summaries
   tf.summary.scalar('d_loss', tf.reduce_mean(errD))
   tf.summary.scalar('g_loss', tf.reduce_mean(errG))
   tf.summary.scalar('l1_loss', tf.reduce_mean(l1_loss))

   # get all trainable variables, and split by network G and network D
   t_vars = tf.trainable_variables()
   d_vars = [var for var in t_vars if 'd_' in var.name]
   g_vars = [var for var in t_vars if 'g_' in var.name]
      
   G_train_op = tf.train.AdamOptimizer(learning_rate=LEARNING_RATE).minimize(errG, var_list=g_vars, global_step=global_step)
   D_train_op = tf.train.AdamOptimizer(learning_rate=LEARNING_RATE).minimize(errD, var_list=d_vars)

   saver = tf.train.Saver(max_to_keep=1)

   init = tf.group(tf.local_variables_initializer(), tf.global_variables_initializer())
   sess = tf.Session()
   sess.run(init)

   # write out logs for tensorboard to the checkpointSdir
   summary_writer = tf.summary.FileWriter(EXPERIMENT_DIR+'/logs/', graph=tf.get_default_graph())

   tf.add_to_collection('vars', G_train_op)
   tf.add_to_collection('vars', D_train_op)

   ckpt = tf.train.get_checkpoint_state(EXPERIMENT_DIR)
   if ckpt and ckpt.model_checkpoint_path:
      print "Restoring previous model..."
      try:
         saver.restore(sess, ckpt.model_checkpoint_path)
         print "Model restored"
      except:
         print "Could not restore model"
         pass
   
   step = int(sess.run(global_step))

   merged_summary_op = tf.summary.merge_all()

   # get train/test data

   # underwater photos
   trainA_paths = np.asarray(glob.glob('datasets/'+DATA+'/trainA/*.jpg'))

   # normal photos (ground truth)
   trainB_paths = np.asarray(glob.glob('datasets/'+DATA+'/trainB/*.jpg'))
   
   # testing paths
   testA_paths = np.asarray(glob.glob('datasets/'+DATA+'/testA/*.jpg'))
   testB_paths = np.asarray(glob.glob('datasets/'+DATA+'/testB/*.jpg'))

   print len(trainB_paths)
   print len(trainA_paths)

   num_train = len(trainB_paths)
   num_test  = len(testB_paths)

   while True:

      idx = np.random.choice(np.arange(num_train), BATCH_SIZE, replace=False)
      batchA_paths = trainA_paths[idx]
      batchB_paths = trainB_paths[idx]
      
      batchA_images = np.empty((BATCH_SIZE, 256, 256, 3), dtype=np.float32)
      batchB_images = np.empty((BATCH_SIZE, 256, 256, 3), dtype=np.float32)

      i = 0
      for a,b in zip(batchA_paths, batchB_paths):
         a_img = data_ops.preprocess(misc.imread(a).astype('float32'))
         b_img = data_ops.preprocess(misc.imread(b).astype('float32'))
         batchA_images[i, ...] = a_img
         batchB_images[i, ...] = b_img
         i += 1

      sess.run(D_train_op, feed_dict={image_u:batchA_images, image_r:batchB_images})
      sess.run(G_train_op, feed_dict={image_u:batchA_images, image_r:batchB_images})
      D_loss, G_loss, summary = sess.run([errD, errG, merged_summary_op], feed_dict={image_u:batchA_images, image_r:batchB_images})

      summary_writer.add_summary(summary, step)
      print 'step:',step,'D loss:',D_loss,'G_loss:',G_loss
      step += 1
      
      if step%500 == 0:
         print 'Saving model...'
         saver.save(sess, EXPERIMENT_DIR+'checkpoint-'+str(step))
         saver.export_meta_graph(EXPERIMENT_DIR+'checkpoint-'+str(step)+'.meta')
         print 'Model saved\n'

         idx = np.random.choice(np.arange(num_test), BATCH_SIZE, replace=False)
         batchA_paths = testA_paths[idx]
         batchB_paths = testB_paths[idx]
         
         batchA_images = np.empty((BATCH_SIZE, 256, 256, 3), dtype=np.float32)
         batchB_images = np.empty((BATCH_SIZE, 256, 256, 3), dtype=np.float32)

         i = 0
         for a,b in zip(batchA_paths, batchB_paths):
            a_img = data_ops.preprocess(misc.imread(a).astype('float32'))
            b_img = data_ops.preprocess(misc.imread(b).astype('float32'))
            batchA_images[i, ...] = a_img
            batchB_images[i, ...] = b_img
            i += 1

         gen_images = np.asarray(sess.run(gen_image, feed_dict={image_u:batchA_images, image_r:batchB_images}))

         for gen, real, cor in zip(gen_images, batchB_images, batchA_images):
            misc.imsave(IMAGES_DIR+str(step)+'_corrupt.png', cor)
            misc.imsave(IMAGES_DIR+str(step)+'_real.png', real)
            misc.imsave(IMAGES_DIR+str(step)+'_gen.png', gen)
            break

# Copyright 2019 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Pseudo-label: The simple and efficient semi-supervised learning method fordeep neural networks.

Reimplementation of http://deeplearning.net/wp-content/uploads/2013/03/pseudo_label_final.pdf
"""

import functools
import os

from absl import app
from absl import flags
from easydict import EasyDict
from libml import utils, data, models
import tensorflow as tf

FLAGS = flags.FLAGS
flags.DEFINE_float('target_loss',None, 'Target Loss to achieve')

class DataDistill(models.MultiModel):

    def model(self, lr, wd, ema, warmup_pos, consistency_weight, threshold, **kwargs):
        hwc = [self.dataset.height, self.dataset.width, self.dataset.colors]
        x_in = tf.placeholder(tf.float32, [None] + hwc, 'x')
        y_in = tf.placeholder(tf.float32, [None] + hwc, 'y')
        l_in = tf.placeholder(tf.int32, [None], 'labels')
        l = tf.one_hot(l_in, self.nclass)
        wd *= lr
        warmup = tf.clip_by_value(tf.to_float(self.step) / (warmup_pos * (FLAGS.train_kimg << 10)), 0, 1)
        target_loss = FLAGS.target_loss

        classifier = functools.partial(self.classifier, **kwargs)
        classifier_t = functools.partial(self.classifier, **kwargs)
        classifier_t1 = functools.partial(self.classifier, **kwargs)
        classifier_s = functools.partial(self.classifier, **kwargs)
        logits_x = classifier_s(x_in, training=True)
        logits_y = classifier_s(y_in, training=True)
        post_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)  # Take only first call to update batch norm.
        y1_in = tf.image.random_flip_left_right(y_in)
        y2_in = y_in
        y3_in = tf.image.random_flip_left_right(y_in)
        logits_y1 = classifier(y1_in, training=True)
        logits_y2 = classifier_t(y2_in, training=True)
        logits_y3 = classifier_t1(y3_in, training=True)
        #only use the label when confidence is high

        gtt1 = tf.reduce_any(
            tf.greater(tf.nn.softmax(logits_y1),threshold),
            axis=-1,
            keepdims=True,
        )
        gtt2 = tf.reduce_any(
            tf.greater(tf.nn.softmax(logits_y2),threshold),
            axis=-1,
            keepdims=True,
        )
        gtt3 = tf.reduce_any(
            tf.greater(tf.nn.softmax(logits_y3),threshold),
            axis=-1,
            keepdims=True,
        )

        # Get the pseudo-label loss
        labels_y1 = tf.argmax(logits_y1, axis=-1)
        labels_y2 = tf.argmax(logits_y2, axis=-1)
        labels_y3 = tf.argmax(logits_y3, axis=-1) 
        labels_y = tf.floor(tf.divide(labels_y1 + labels_y2 + labels_y3, 3)) 
        labels_y = tf.dtypes.cast(labels_y,tf.int32)
        labels_y = tf.one_hot(labels_y, self.nclass)
        #labels_y = tf.reduce_mean([labels_y1,labels_y2,labels_y3])
        #labels_y = tf.reduce_all([labels_y1,labels_y2,labels_y3])
        l1 = tf.concat([l,labels_y],0)
        logits_x1 = tf.concat([logits_x,logits_y],0)
        print(l1)
        print(logits_x1)
        loss = tf.nn.softmax_cross_entropy_with_logits_v2(labels=l1, logits=logits_x1)
        loss = tf.reduce_mean(loss)
        if (target_loss != None and loss < target_loss):
            print("TODO:target_loss logs not yet implemented!")
            exit(0)
        tf.summary.scalar('losses/xe', loss)

        train_op = tf.train.AdamOptimizer(lr).minimize(loss,
                                                       colocate_gradients_with_ops=True)
        with tf.control_dependencies([train_op]):
            train_op = tf.group(*post_ops)

        # Tuning op: only retrain batch norm.
        skip_ops = tf.get_collection(tf.GraphKeys.UPDATE_OPS)
        classifier(x_in, training=True)
        train_bn = tf.group(*[v for v in tf.get_collection(tf.GraphKeys.UPDATE_OPS)
                              if v not in skip_ops])

        return EasyDict(
            x=x_in, y=y_in, label=l_in, train_op=train_op, tune_op=train_bn,
            classify_raw=tf.nn.softmax(classifier(x_in, training=False)),  # No EMA, for debugging.
            classify_op=tf.nn.softmax(classifier(x_in, training=False)))


def main(argv):
    del argv  # Unused.
    dataset = data.DATASETS[FLAGS.dataset]()
    log_width = utils.ilog2(dataset.width)
    model = DataDistill(
        os.path.join(FLAGS.train_dir, dataset.name),
        dataset,
        lr=FLAGS.lr,
        wd=FLAGS.wd,
        arch=FLAGS.arch,
        warmup_pos=FLAGS.warmup_pos,
        batch=FLAGS.batch,
        nclass=dataset.nclass,
        ema=FLAGS.ema,
        smoothing=FLAGS.smoothing,
        consistency_weight=FLAGS.consistency_weight,
        threshold=FLAGS.threshold,

        scales=FLAGS.scales or (log_width - 2),
        filters=FLAGS.filters,
        repeat=FLAGS.repeat)
    model.train(FLAGS.train_kimg << 10, FLAGS.report_kimg << 10)


if __name__ == '__main__':
    utils.setup_tf()
    flags.DEFINE_float('wd', 0.02, 'Weight decay.')
    flags.DEFINE_float('consistency_weight', 1., 'Consistency weight.')
    flags.DEFINE_float('threshold', 0.95, 'Pseudo-label threshold.')
    flags.DEFINE_float('warmup_pos', 0.4, 'Relative position at which constraint loss warmup ends.')
    flags.DEFINE_float('ema', 0.999, 'Exponential moving average of params.')
    flags.DEFINE_float('smoothing', 0.1, 'Label smoothing.')
    flags.DEFINE_integer('scales', 0, 'Number of 2x2 downscalings in the classifier.')
    flags.DEFINE_integer('filters', 32, 'Filter size of convolutions.')
    flags.DEFINE_integer('repeat', 4, 'Number of residual layers per stage.')
    FLAGS.set_default('dataset', 'cifar10.3@250-5000')
    FLAGS.set_default('batch', 64)
    FLAGS.set_default('lr', 0.002)
    FLAGS.set_default('train_kimg', 1 << 16)
    app.run(main)

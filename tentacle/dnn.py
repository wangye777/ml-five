import collections
import csv
import gc
import os

import psutil
from scipy import ndimage

import numpy as np
import tensorflow as tf
from tentacle.board import Board
from tentacle.data_set import DataSet


Datasets = collections.namedtuple('Dataset', ['train', 'validation', 'test'])

class RingBuffer():
    "A 1D ring buffer using numpy arrays"
    def __init__(self, length):
        self.data = np.zeros(length, dtype='f')
        self.index = 0

    def extend(self, x):
        "adds array x to ring buffer"
        x_index = (self.index + np.arange(x.size)) % self.data.size
        self.data[x_index] = x
        self.index = x_index[-1] + 1

    def get_average(self):
        return np.average(self.data)


class Pre(object):
    NUM_ACTIONS = Board.BOARD_SIZE_SQ
    NUM_CHANNELS = 3

    BATCH_SIZE = 100
    LEARNING_RATE = 0.001
    NUM_STEPS = 3000
    DATASET_CAPACITY = 300000

    TRAIN_DIR = '/home/splendor/fusor/brain/'
    SUMMARY_DIR = '/home/splendor/fusor/summary'
    STAT_FILE = '/home/splendor/glycogen/stat.npz'
    DATA_SET_FILE = 'dataset_9x9_dilated.txt'


    def __init__(self, is_train=True, is_revive=False):
        self.is_train = is_train
        self.is_revive = is_revive
        self._file_read_index = 0
        self._has_more_data = True
        self.ds = None
        self.gstep = 0
        self.loss_window = RingBuffer(10)
        self.stat = []

    def placeholder_inputs(self):
        h, w, c = self.get_input_shape()
        states = tf.placeholder(tf.float32, [None, h, w, c])  # NHWC
        actions = tf.placeholder(tf.int64, [None])
        return states, actions

    def weight_variable(self, shape):
        initial = tf.truncated_normal(shape, stddev=0.1)
        return tf.Variable(initial)

    def bias_variable(self, shape):
        initial = tf.constant(0.1, shape=shape)
        return tf.Variable(initial)

    def model(self, states_pl, actions_pl):
        # HWC,outC
        ch1 = 20
        W_1 = self.weight_variable([5, 5, Pre.NUM_CHANNELS, ch1])
        b_1 = self.bias_variable([ch1])
        ch = 28
        W_2 = self.weight_variable([3, 3, ch1, ch])
        b_2 = self.bias_variable([ch])
        W_21 = self.weight_variable([3, 3, ch, ch])
        b_21 = self.bias_variable([ch])
        W_22 = self.weight_variable([3, 3, ch, ch])
        b_22 = self.bias_variable([ch])
        W_23 = self.weight_variable([3, 3, ch, ch])
        b_23 = self.bias_variable([ch])
        W_24 = self.weight_variable([3, 3, ch, ch])
        b_24 = self.bias_variable([ch])
        W_25 = self.weight_variable([3, 3, ch, ch])
        b_25 = self.bias_variable([ch])
        W_26 = self.weight_variable([3, 3, ch, ch])
        b_26 = self.bias_variable([ch])
        W_27 = self.weight_variable([3, 3, ch, ch])
        b_27 = self.bias_variable([ch])
        W_28 = self.weight_variable([3, 3, ch, ch])
        b_28 = self.bias_variable([ch])
        W_29 = self.weight_variable([3, 3, ch, ch])
        b_29 = self.bias_variable([ch])

        h_conv1 = tf.nn.relu(tf.nn.conv2d(states_pl, W_1, [1, 2, 2, 1], padding='SAME') + b_1)
        h_conv2 = tf.nn.relu(tf.nn.conv2d(h_conv1, W_2, [1, 1, 1, 1], padding='SAME') + b_2)
        h_conv21 = tf.nn.relu(tf.nn.conv2d(h_conv2, W_21, [1, 1, 1, 1], padding='SAME') + b_21)
        h_conv22 = tf.nn.relu(tf.nn.conv2d(h_conv21, W_22, [1, 1, 1, 1], padding='SAME') + b_22)
        h_conv23 = tf.nn.relu(tf.nn.conv2d(h_conv22, W_23, [1, 1, 1, 1], padding='SAME') + b_23)
        h_conv24 = tf.nn.relu(tf.nn.conv2d(h_conv23, W_24, [1, 1, 1, 1], padding='SAME') + b_24)
        h_conv25 = tf.nn.relu(tf.nn.conv2d(h_conv24, W_25, [1, 1, 1, 1], padding='SAME') + b_25)
        h_conv26 = tf.nn.relu(tf.nn.conv2d(h_conv25, W_26, [1, 1, 1, 1], padding='SAME') + b_26)
        h_conv27 = tf.nn.relu(tf.nn.conv2d(h_conv26, W_27, [1, 1, 1, 1], padding='SAME') + b_27)
        h_conv28 = tf.nn.relu(tf.nn.conv2d(h_conv27, W_28, [1, 1, 1, 1], padding='SAME') + b_28)
        h_conv29 = tf.nn.relu(tf.nn.conv2d(h_conv28, W_29, [1, 1, 1, 1], padding='SAME') + b_29)

        shape = h_conv29.get_shape().as_list()
        dim = np.cumprod(shape[1:])[-1]
        h_conv_out = tf.reshape(h_conv29, [-1, dim])

        num_hidden = 64
        W_3 = self.weight_variable([dim, num_hidden])
        b_3 = self.bias_variable([num_hidden])
        W_4 = self.weight_variable([num_hidden, Pre.NUM_ACTIONS])
        b_4 = self.bias_variable([Pre.NUM_ACTIONS])

        hidden = tf.nn.relu(tf.matmul(h_conv_out, W_3) + b_3)
        predictions = tf.matmul(hidden, W_4) + b_4

        cross_entropy = tf.nn.sparse_softmax_cross_entropy_with_logits(predictions, actions_pl)
        self.loss = tf.reduce_mean(cross_entropy)
        tf.scalar_summary("loss", self.loss)
        self.optimizer = tf.train.AdadeltaOptimizer(Pre.LEARNING_RATE).minimize(self.loss)

        self.predict_probs = tf.nn.softmax(predictions)
        eq = tf.equal(tf.argmax(self.predict_probs, 1), actions_pl)
        self.eval_correct = tf.reduce_sum(tf.cast(eq, tf.int32))

    def prepare(self):
        self.states_pl, self.actions_pl = self.placeholder_inputs()
        self.model(self.states_pl, self.actions_pl)

        self.summary_op = tf.merge_all_summaries()

        self.saver = tf.train.Saver()

        init = tf.initialize_all_variables()
        self.sess = tf.Session()
        self.summary_writer = tf.train.SummaryWriter(Pre.SUMMARY_DIR, self.sess.graph)

        self.sess.run(init)
        print('Initialized')

    def load_from_vat(self):
        ckpt = tf.train.get_checkpoint_state(Pre.TRAIN_DIR)
        if ckpt and ckpt.model_checkpoint_path:
            self.saver.restore(self.sess, ckpt.model_checkpoint_path)

    def fill_feed_dict(self, data_set, states_pl, actions_pl, batch_size=None):
        batch_size = batch_size or Pre.BATCH_SIZE
        states_feed, actions_feed = data_set.next_batch(batch_size)
        feed_dict = {
            states_pl: states_feed,
            actions_pl: actions_feed.ravel(),
        }
        return feed_dict

    def do_eval(self, eval_correct, states_pl, actions_pl, data_set):
        true_count = 0  # Counts the number of correct predictions.
        batch_size = Pre.BATCH_SIZE
        steps_per_epoch = data_set.num_examples // batch_size
        num_examples = steps_per_epoch * batch_size
        for _ in range(steps_per_epoch):
            feed_dict = self.fill_feed_dict(data_set, states_pl, actions_pl, batch_size)
            true_count += self.sess.run(eval_correct, feed_dict=feed_dict)
        precision = true_count / num_examples
        return precision

    def get_move_probs(self, state):
        h, w, c = self.get_input_shape()
        feed_dict = {
            self.states_pl: state.reshape(1, -1).reshape((-1, h, w, c)),
            self.actions_pl: np.zeros(1)
        }
        return self.sess.run(self.predict_probs, feed_dict=feed_dict)

    def train(self):
        for step in range(Pre.NUM_STEPS):
            feed_dict = self.fill_feed_dict(self.ds.train, self.states_pl, self.actions_pl)
            _, loss = self.sess.run([self.optimizer, self.loss], feed_dict=feed_dict)
            self.loss_window.extend(loss)

            self.gstep += 1
            step += 1

            if (step % 100 == 0):
                summary_str = self.sess.run(self.summary_op, feed_dict=feed_dict)
                self.summary_writer.add_summary(summary_str, self.gstep)
                self.summary_writer.flush()

            if (step + 1) % 1000 == 0 or (step + 1) == Pre.NUM_STEPS:
                self.saver.save(self.sess, Pre.TRAIN_DIR + 'model.ckpt', global_step=self.gstep)
                train_accuracy = self.do_eval(self.eval_correct, self.states_pl, self.actions_pl, self.ds.train)
                validation_accuracy = self.do_eval(self.eval_correct, self.states_pl, self.actions_pl, self.ds.validation)
                self.stat.append((self.gstep, train_accuracy, validation_accuracy, 0., Pre.DATASET_CAPACITY))
#                 print('step: ', self.gstep)

        test_accuracy = self.do_eval(self.eval_correct, self.states_pl, self.actions_pl, self.ds.test)
        print('test accuracy:', test_accuracy)

        np.savez(Pre.STAT_FILE, stat=np.array(self.stat))


    def adapt(self, filename):
        ds = []
        dat = self.load_dataset(filename)
        for row in dat:
            s, a = self.forge(row)
            ds.append((s, a))

        ds = np.array(ds)

        np.random.shuffle(ds)

        size = ds.shape[0]
        train_size = int(size * 0.8)
        train = ds[:train_size, :]
        test = ds[train_size:, :]

        validation_size = int(train.shape[0] * 0.2)
        validation = train[:validation_size, :]
        train = train[validation_size:, :]

        h, w, c = self.get_input_shape()
        train = DataSet(np.vstack(train[:, 0]).reshape((-1, h, w, c)), np.vstack(train[:, 1]))
        validation = DataSet(np.vstack(validation[:, 0]).reshape((-1, h, w, c)), np.vstack(validation[:, 1]))
        test = DataSet(np.vstack(test[:, 0]).reshape((-1, h, w, c)), np.vstack(test[:, 1]))

        print(train.images.shape, train.labels.shape)
        print(validation.images.shape, validation.labels.shape)
        print(test.images.shape, test.labels.shape)

        self.ds = Datasets(train=train, validation=validation, test=test)

    def get_input_shape(self):
        return Board.BOARD_SIZE, Board.BOARD_SIZE, Pre.NUM_CHANNELS

    def load_dataset(self, filename):
        proc = psutil.Process(os.getpid())
        gc.collect()
        mem0 = proc.memory_info().rss

        del self.ds
        gc.collect()

        mem1 = proc.memory_info().rss
        print('gc(M): ', (mem1 - mem0) / 1024 ** 2)

        content = []
        with open(filename) as csvfile:
            reader = csv.reader(csvfile)
            for index, line in enumerate(reader):
                if index >= self._file_read_index:
                    if index < self._file_read_index + Pre.DATASET_CAPACITY:
                        content.append([float(i) for i in line])
                    else:
                        break
            if index == self._file_read_index + Pre.DATASET_CAPACITY:
                self._has_more_data = True
                self._file_read_index += Pre.DATASET_CAPACITY
            else:
                self._has_more_data = False

        content = np.array(content)

        print('load data:', content.shape)

        # unique board position
        a = content[:, :-4]
        b = np.ascontiguousarray(a).view(np.dtype((np.void, a.dtype.itemsize * a.shape[1])))
        _, idx = np.unique(b, return_index=True)
        unique_a = content[idx]
        print('unique:', unique_a.shape)
        return unique_a


    def _neighbor_count(self, board, who):
        footprint = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]])
        return ndimage.generic_filter(board, lambda r: np.count_nonzero(r == who), footprint=footprint, mode='constant')

    def adapt_state(self, board):
        black = (board == Board.STONE_BLACK).astype(float)
        white = (board == Board.STONE_WHITE).astype(float)
        empty = (board == Board.STONE_EMPTY).astype(float)

        image = np.dstack((black, white, empty)).ravel()
        legal = empty.astype(bool)
        return image, legal

    def forge(self, row):
        board = row[:Board.BOARD_SIZE_SQ]
        image, _ = self.adapt_state(board)

        move = tuple(row[-4:-2].astype(int))
        move = np.ravel_multi_index(move, (Board.BOARD_SIZE, Board.BOARD_SIZE))

        return image, move

    def close(self):
        if self.sess is not None:
            self.sess.close()

    def run(self):
        self.prepare()

        if self.is_revive:
            self.load_from_vat()

        if self.is_train:
            epoch = 0
            while self.loss_window.get_average() == 0.0 or self.loss_window.get_average() > 0.5:
                print('epoch: ', epoch)
                epoch += 1
                while self._has_more_data:
                    self.adapt(Pre.DATA_SET_FILE)
                    self.train()
                # reset
                self._file_read_index = 0
                self._has_more_data = True
#                 if epoch >= 1:
#                     break


if __name__ == '__main__':
    pre = Pre()
    pre.run()

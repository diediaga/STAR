# -*- coding: utf-8 -*-
""" 
Usage:
    THEANO_FLAGS="device=gpu0" python exptTaxiBJ.py [number_of_residual_units]
"""
from __future__ import print_function
import os
import sys
import pickle as pickle
import time
import h5py

import star.metrics as metrics
from keras.optimizers import Adam
from keras.callbacks import EarlyStopping, ModelCheckpoint, TensorBoard, CSVLogger
from star.model import *
from star.config import Config
from star import TaxiBJ
from star.multi_step import *
np.random.seed(1337)  # for reproducibility

# parameters
DATAPATH = Config().DATAPATH  # data path, you may set your own data path with the global envirmental variable DATAPATH
CACHEDATA = True  # cache data or NOT
path_cache = os.path.join(DATAPATH, 'CACHE')  # cache path
nb_epoch = 100 # number of epoch at training stage
nb_epoch_cont =  100 # number of epoch at training (cont) stage
batch_size = 16  # batch size
T = 48  # number of time intervals in one day
lr = 0.00015 # learning rate

len_closeness = 3 # length of closeness dependent sequence
len_period = 1 # length of peroid dependent sequence
len_trend = 1 # length of trend dependent sequence

if len(sys.argv) == 1:
    print(__doc__)
    sys.exit(-1)
    # nb_residual_unit = 2  # number of residual units
else:
    nb_residual_unit = int(sys.argv[1]) # number of residual units

nb_flow = 2  # there are two types of flows: inflow and outflow
# divide data into two subsets: Train & Test, of which the test set is the
# last 4 weeks
days_test = 7*4
len_test = T*days_test
len_val = 2*len_test
map_height, map_width = 32, 32  # grid size

path_result = os.path.join('RET', 'BJ')
path_model = os.path.join('MODEL', 'BJ')
path_log = 'log_BJ'
muilt_step = False

for path in [path_result, path_model, path_log]:
    os.makedirs(path, exist_ok=True)

if CACHEDATA and not os.path.isdir(path_cache):
    os.mkdir(path_cache)

def build_model(external_dim):
    c_conf = (len_closeness, nb_flow, map_height,
              map_width) if len_closeness > 0 else None
    p_conf = (len_period, nb_flow, map_height,
              map_width) if len_period > 0 else None
    t_conf = (len_trend, nb_flow, map_height,
              map_width) if len_trend > 0 else None
    model = STAR(c_conf=c_conf, p_conf=p_conf, t_conf=t_conf,
                     external_dim=external_dim, nb_residual_unit=nb_residual_unit)
    # sgd = SGD(lr=lr, momentum=0.9, decay=5e-4, nesterov=True)
    adam = Adam(lr=lr)
    model.compile(loss='mse', optimizer=adam, metrics=[metrics.rmse])
    # model.summary()

    # from keras.utils.vis_utils import plot_model
    # plot_model(model, to_file='/home/suhan/wanghn/BJ_model.png', show_shapes=True)

    return model

def read_cache(fname):
    mmn = pickle.load(open('preprocessing_bj.pkl', 'rb'))

    f = h5py.File(fname, 'r')
    num = int(f['num'].value)
    X_train_all, Y_train_all, X_train, Y_train, X_val, Y_val, X_test, Y_test = [], [], [], [], [], [], [], []
    for i in range(num):
        X_train_all.append(f['X_train_all_%i' % i].value)
        X_train.append(f['X_train_%i' % i].value)
        X_val.append(f['X_val_%i' % i].value)
        X_test.append(f['X_test_%i' % i].value)
    Y_train_all = f['Y_train_all'].value
    Y_train = f['Y_train'].value
    Y_val = f['Y_val'].value
    Y_test = f['Y_test'].value
    external_dim = f['external_dim'].value
    timestamp_train_all = f['T_train_all'].value
    timestamp_train = f['T_train'].value
    timestamp_val = f['T_val'].value
    timestamp_test = f['T_test'].value
    f.close()

    return X_train_all, Y_train_all, X_train, Y_train, X_val, Y_val, X_test, Y_test, mmn, external_dim, timestamp_train_all, timestamp_train, timestamp_val, timestamp_test


def cache(fname, X_train_all, Y_train_all, X_train, Y_train, X_val, Y_val, X_test, Y_test, external_dim, timestamp_train_all, timestamp_train, timestamp_val, timestamp_test):
    h5 = h5py.File(fname, 'w')
    h5.create_dataset('num', data=len(X_train_all))

    for i, data in enumerate(X_train_all):
        h5.create_dataset('X_train_all_%i' % i, data=data)
    for i, data in enumerate(X_train):
        h5.create_dataset('X_train_%i' % i, data=data)
    for i, data in enumerate(X_val):
        h5.create_dataset('X_val_%i' % i, data=data)
    # for i, data in enumerate(Y_train):
    for i, data in enumerate(X_test):
        h5.create_dataset('X_test_%i' % i, data=data)

    h5.create_dataset('Y_train_all', data=Y_train_all)
    h5.create_dataset('Y_train', data=Y_train)
    h5.create_dataset('Y_val', data=Y_val)
    h5.create_dataset('Y_test', data=Y_test)
    external_dim = -1 if external_dim is None else int(external_dim)
    h5.create_dataset('external_dim', data=external_dim)
    h5.create_dataset('T_train_all', data=timestamp_train_all)
    h5.create_dataset('T_train', data=timestamp_train)
    h5.create_dataset('T_val', data=timestamp_val)
    h5.create_dataset('T_test', data=timestamp_test)
    h5.close()


def main():
    if muilt_step:
        dic_rmse={}
        list_muilt_rmse=[]
    for i in range(0,10):
        print("loading data...")
        ts = time.time()
        fname = os.path.join(DATAPATH, 'CACHE', 'TaxiBJ_C{}_P{}_T{}.h5'.format(
            len_closeness, len_period, len_trend))
        if os.path.exists(fname) and CACHEDATA:
            X_train_all, Y_train_all, X_train, Y_train, \
            X_val, Y_val, X_test, Y_test, mmn, external_dim, \
            timestamp_train_all, timestamp_train, timestamp_val, timestamp_test = read_cache(
                fname)
            print("load %s successfully" % fname)
        else:
            X_train_all, Y_train_all, X_train, Y_train, \
            X_val, Y_val, X_test, Y_test, mmn, external_dim, \
            timestamp_train_all, timestamp_train, timestamp_val, timestamp_test = TaxiBJ.load_data(
                T=T, nb_flow=nb_flow, len_closeness=len_closeness, len_period=len_period, len_trend=len_trend, len_test=len_test,
                len_val=len_val, preprocess_name='preprocessing_bj.pkl', meta_data=True, meteorol_data=False, holiday_data=False)
            if CACHEDATA:
                cache(fname, X_train_all, Y_train_all, X_train, Y_train, X_val, Y_val, X_test, Y_test,
                      external_dim, timestamp_train_all, timestamp_train, timestamp_val, timestamp_test)
        print(external_dim)
        print("\n days (test): ", [v[:8] for v in timestamp_test[0::T]])
        print("\nelapsed time (loading data): %.3f seconds\n" % (time.time() - ts))

        print('=' * 10)
        print("compiling model...")

        ts = time.time()
        print('external dim:', external_dim)

        model = build_model(external_dim)

        hyperparams_name = 'c{}.p{}.t{}.resunit{}.lr{}.iter{}'.format(
            len_closeness, len_period, len_trend, nb_residual_unit, lr, i)
        fname_param = os.path.join(path_model, '{}.best.h5'.format(hyperparams_name))

        csv = CSVLogger(os.path.join(path_result, hyperparams_name+'.csv'), separator=',', append=False)
        early_stopping = EarlyStopping(monitor='val_rmse', patience=4, mode='min')#4
        model_checkpoint = ModelCheckpoint(
            fname_param, monitor='val_rmse', verbose=2, save_best_only=True, mode='min')

        print("\nelapsed time (compiling model): %.3f seconds\n" %
              (time.time() - ts))
        history = model.fit(X_train, Y_train,
                            epochs=nb_epoch,
                            batch_size=batch_size,
                            # validation_split=0.15,
                            validation_data=(X_val,Y_val),
                            callbacks=[TensorBoard(log_dir=os.path.join(path_log, '{}_step1_plot_{}'.format(hyperparams_name, i))),
                                       early_stopping,
                                       model_checkpoint],
                            verbose=2)

        model.save_weights(os.path.join(
            path_model, '{}.h5'.format(hyperparams_name)), overwrite=True)

        pickle.dump((history.history), open(os.path.join(
            path_result, '{}.history.pkl'.format(hyperparams_name)), 'wb'))
        print("\nelapsed time (training): %.3f seconds\n" % (time.time() - ts))

        print('=' * 10)
        print('evaluating using the model that has the best loss on the valid set')
        ts = time.time()
        model.load_weights(fname_param)
        score = model.evaluate(X_train, Y_train, batch_size=8, verbose=0)
        print('Train score: %.6f rmse (norm): %.6f rmse (real): %.6f' %
              (score[0], score[1], score[1] * (mmn._max - mmn._min) / 2.))
        score = model.evaluate(
            X_test, Y_test, batch_size=8, verbose=0)
        print('Test score: %.6f rmse (norm): %.6f rmse (real): %.6f' %
              (score[0], score[1], score[1] * (mmn._max - mmn._min) / 2.))
        print("\nelapsed time (eval): %.3f seconds\n" % (time.time() - ts))

        print('=' * 10)
        print("training model (cont)...")
        ts = time.time()
        fname_param = os.path.join(
            path_model, '{}.cont.best.h5'.format(hyperparams_name))
        model_checkpoint = ModelCheckpoint(
            fname_param, monitor='rmse', verbose=0, save_best_only=True, mode='min')

        history = model.fit(X_train_all, Y_train_all, 
                            epochs=nb_epoch_cont, 
                            verbose=2, 
                            batch_size=batch_size, 
                            validation_data=(X_test,Y_test),
                            callbacks=[TensorBoard(log_dir=os.path.join(path_log, '{}_step2_plot_{}'.format(hyperparams_name, i))),
                                       csv,
                                       model_checkpoint])
        pickle.dump((history.history), open(os.path.join(
            path_result, '{}.cont.history.pkl'.format(hyperparams_name)), 'wb'))
        model.save_weights(os.path.join(
            path_model, '{}_cont.h5'.format(hyperparams_name)), overwrite=True)
        print("\nelapsed time (training cont): %.3f seconds\n" % (time.time() - ts))

        print('=' * 10)
        print('evaluating using the final model')
        score = model.evaluate(X_train_all, Y_train_all, batch_size=1, verbose=0)
        print('Train score: %.6f rmse (norm): %.6f rmse (real): %.6f' %
              (score[0], score[1], score[1] * (mmn._max - mmn._min) / 2.))
        ts = time.time()
        score = model.evaluate(
            X_test, Y_test, batch_size=Y_test.shape[0], verbose=0)
        print('Test score: %.6f rmse (norm): %.6f rmse (real): %.6f' %
              (score[0], score[1], score[1] * (mmn._max - mmn._min) / 2.))
        print("\nelapsed time (eval cont): %.3f seconds\n" % (time.time() - ts))
        
        if muilt_step:
            ts = time.time()
            dic_muilt_rmse = multi_step_2D(model, path_model, hyperparams_name, X_test, Y_test, 12)
            print("\nelapsed time (multi): %.3f seconds\n" % (time.time() - ts))
            list_muilt_rmse.append(dic_muilt_rmse)
            dic_rmse[hyperparams_name] = score[1] * (mmn._max - mmn._min) / 2.
    if muilt_step:    
        print(sorted(dic_rmse.items(), key=lambda item:item[1]))
        for j in list_muilt_rmse:
            print("\n", j)
if __name__ == '__main__':
    main()

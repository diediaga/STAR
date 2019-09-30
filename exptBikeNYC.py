# -*- coding: utf-8 -*-
""" 
Usage:
    THEANO_FLAGS="device=gpu0" python exptBikeNYC.py
"""
from __future__ import print_function
import os
import _pickle as pickle
import numpy as np
import math
import h5py

from keras.optimizers import Adam
from keras.callbacks import EarlyStopping, ModelCheckpoint,TensorBoard, LearningRateScheduler
from star.model import *
from star.config import Config
import star.metrics as metrics
from star import BikeNYC

np.random.seed(1337)  # for reproducibility

# parameters
# data path, you may set your own data path with the global envirmental
# variable DATAPATH
DATAPATH = Config().DATAPATH
nb_epoch = 200  # number of epoch at training stage
nb_epoch_cont = 150  # number of epoch at training (cont) stage
batch_size = 16  # batch size
T = 24  # number of time intervals in one day
CACHEDATA = True  # cache data or NOT

lr = 0.00015  # learning rate
len_closeness = 3  # length of closeness dependent sequence
len_period = 1  # length of peroid dependent sequence
len_trend = 1  # length of trend dependent sequence
nb_residual_unit = 2   # number of residual units

nb_flow = 2  # there are two types of flows: new-flow and end-flow
# divide data into two subsets: Train & Test, of which the test set is the
# last 10 days
days_test = 10
len_test = T*days_test
len_val = 2*len_test

map_height, map_width = 16, 8  # grid size
# For NYC Bike data, there are 81 available grid-based areas, each of
# which includes at least ONE bike station. Therefore, we modify the final
# RMSE by multiplying the following factor (i.e., factor).
nb_area = 81
m_factor = math.sqrt(1. * map_height * map_width / nb_area)
print('factor: ', m_factor)
path_result = os.path.join('RET', 'NYC')
path_model = os.path.join('MODEL', 'NYC')

for path in [path_result, path_model]:
    if os.path.isdir(path) is False:
        os.mkdir(path)


def read_cache(fname):
    mmn = pickle.load(open('preprocessing_nyc.pkl', 'rb'))

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

def build_model(external_dim):
    c_conf = (len_closeness, nb_flow, map_height,
              map_width) if len_closeness > 0 else None
    p_conf = (len_period, nb_flow, map_height,
              map_width) if len_period > 0 else None
    t_conf = (len_trend, nb_flow, map_height,
              map_width) if len_trend > 0 else None

    model = STAR(c_conf=c_conf, p_conf=p_conf, t_conf=t_conf,
                     external_dim=external_dim, nb_residual_unit=nb_residual_unit)
    adam = Adam(lr=lr)
    model.compile(loss='mse', optimizer=adam, metrics=[metrics.rmse])
    # model.summary()

    # from keras.utils.vis_utils import plot_model
    # plot(model, to_file='NYC_model.png', show_shapes=True)

    return model

def lrschedule(epoch):
    if epoch <= 25:
        return 0.0002
    elif epoch <= 50:
        return 0.00015
    elif epoch <= 75:
        return 0.0001
    elif epoch <= 100:
        return 0.00005
    else: return 0.00001

def main():
    dic_rmse = {}
    for i in range(0,10):
        print("loading data...")
        fname = os.path.join(DATAPATH, 'CACHE', 'BikeNYC_C{}_P{}_T{}.h5'.format(
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
            timestamp_train_all, timestamp_train, timestamp_val, timestamp_test = BikeNYC.load_data(
                T=T, nb_flow=nb_flow, len_closeness=len_closeness, len_period=len_period, len_trend=len_trend, len_test=len_test,
                len_val=len_val, preprocess_name='preprocessing_nyc.pkl', meta_data=True)
            if CACHEDATA:
                cache(fname, X_train_all, Y_train_all, X_train, Y_train, X_val, Y_val, X_test, Y_test,
                      external_dim, timestamp_train_all, timestamp_train, timestamp_val, timestamp_test)

        print("\n days (test): ", [v[:8] for v in timestamp_test[0::T]])

        print('=' * 10)
        print("compiling model...")

        lr = LearningRateScheduler(lrschedule)

        model = build_model(external_dim)

        hyperparams_name = 'c{}.p{}.t{}.resunit{}.iter{}'.format(
            len_closeness, len_period, len_trend, nb_residual_unit, i)
        fname_param = os.path.join(path_model, '{}.best.h5'.format(hyperparams_name))
        print(hyperparams_name)

        early_stopping = EarlyStopping(monitor='val_rmse', patience=4, mode='min')
        model_checkpoint = ModelCheckpoint(
            fname_param, monitor='val_rmse', verbose=0, save_best_only=True, mode='min')

        print('=' * 10)
        print("training model...")
        history = model.fit(X_train, Y_train,
                            epochs=nb_epoch,
                            batch_size=batch_size,
                            validation_data=(X_val,Y_val),
                            callbacks=[early_stopping, model_checkpoint],
                            verbose=2)
        model.save_weights(os.path.join(
            path_model, '{}.h5'.format(hyperparams_name)), overwrite=True)
        pickle.dump((history.history), open(os.path.join(
            path_result, '{}.history.pkl'.format(hyperparams_name)), 'wb'))

        print('=' * 10)
        print('evaluating using the model that has the best loss on the valid set')

        model.load_weights(fname_param)
        score = model.evaluate(X_train, Y_train, batch_size=Y_train.shape[
                               0] // 48, verbose=0)
        print('Train score: %.6f rmse (norm): %.6f rmse (real): %.6f' %
              (score[0], score[1], score[1] * (mmn._max - mmn._min) / 2. * m_factor))

        score = model.evaluate(
            X_test, Y_test, batch_size=Y_test.shape[0], verbose=0)
        print('Test score: %.6f rmse (norm): %.6f rmse (real): %.6f' %
              (score[0], score[1], score[1] * (mmn._max - mmn._min) / 2. * m_factor))

        print('=' * 10)
        print("training model (cont)...")
        fname_param = os.path.join(
            path_model, '{}.cont.best.h5'.format(hyperparams_name))
        model_checkpoint = ModelCheckpoint(
            fname_param, monitor='rmse', verbose=0, save_best_only=True, mode='min')
        history = model.fit(X_train_all, Y_train_all,
                            nb_epoch=nb_epoch_cont,
                            verbose=2,
                            batch_size=batch_size,
                            callbacks=[lr, model_checkpoint],
                            validation_data=(X_test, Y_test))
        pickle.dump((history.history), open(os.path.join(
            path_result, '{}.cont.history.pkl'.format(hyperparams_name)), 'wb'))
        model.save_weights(os.path.join(
            path_model, '{}_cont.h5'.format(hyperparams_name)), overwrite=True)

        print('=' * 10)
        print('evaluating using the final model')
        score = model.evaluate(X_train_all, Y_train_all, batch_size=Y_train.shape[
                               0] // 48, verbose=0)
        print('Train score: %.6f rmse (norm): %.6f rmse (real): %.6f' %
              (score[0], score[1], score[1] * (mmn._max - mmn._min) / 2. * m_factor))

        score = model.evaluate(
            X_test, Y_test, batch_size=Y_test.shape[0], verbose=0)
        print('Test score: %.6f rmse (norm): %.6f rmse (real): %.6f' %
              (score[0], score[1], score[1] * (mmn._max - mmn._min) / 2. * m_factor))
        # dic_rmse[hyperparams_name] = score[1] * (mmn._max - mmn._min) / 2. * m_factor
    # os.system('rm /home/suhan/wanghn/DeepST/data/CACHE/'+'BikeNYC_C{}_P{}_T{}.h5'.format(
            # len_closeness, len_period, len_trend))
    # print(sorted(dic_rmse.items(), key=lambda item:item[1]))

if __name__ == '__main__':
    main()

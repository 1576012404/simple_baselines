import tensorflow as tf
import numpy as np
from simple_baselines.utils import fc,ortho_init,lstm,batch_to_seq,seq_to_batch
from simple_baselines import utils as utils

mapping={}

def register(name):
    def _thunk(func):
        mapping[name]=func
        return func
    return _thunk


@register("mlp")
def mlp(num_layers=2,num_hidden=64,activation=tf.tanh,layer_norm=False):
    def network_fun(X):
        h=tf.layers.flatten(X)
        for i in range(num_layers):
            h=fc(h,"mlp_fc{}".format(i),nh=num_hidden,init_scale=np.sqrt(2))
            if layer_norm:
                h=tf.contrib.layers.layer_norm(h,center=True,scale=True)
            h=activation(h)
        return h
    return network_fun


def conv(x, scope, *, nf, rf, stride, pad='VALID', init_scale=1.0, data_format='NHWC', one_dim_bias=False):
    if data_format == 'NHWC':
        channel_ax = 3
        strides = [1, stride, stride, 1]
        bshape = [1, 1, 1, nf]
    elif data_format == 'NCHW':
        channel_ax = 1
        strides = [1, 1, stride, stride]
        bshape = [1, nf, 1, 1]
    else:
        raise NotImplementedError
    bias_var_shape = [nf] if one_dim_bias else [1, nf, 1, 1]
    nin = x.get_shape()[channel_ax].value
    wshape = [rf, rf, nin, nf]
    with tf.variable_scope(scope):
        w = tf.get_variable("w", wshape, initializer=ortho_init(init_scale))
        b = tf.get_variable("b", bias_var_shape, initializer=tf.constant_initializer(0.0))
        if not one_dim_bias and data_format == 'NHWC':
            b = tf.reshape(b, bshape)
        return tf.nn.conv2d(x, w, strides=strides, padding=pad, data_format=data_format) + b

def conv_to_fc(x):
    nh = np.prod([v.value for v in x.get_shape()[1:]])
    x = tf.reshape(x, [-1, nh])
    return x


def nature_cnn(unscaled_images, **conv_kwargs):
    """
    CNN from Nature paper.
    """
    scaled_images = tf.cast(unscaled_images, tf.float32) / 255.
    activ = tf.nn.relu
    h = activ(conv(scaled_images, 'c1', nf=32, rf=8, stride=4, init_scale=np.sqrt(2),
                   **conv_kwargs))
    h2 = activ(conv(h, 'c2', nf=64, rf=4, stride=2, init_scale=np.sqrt(2), **conv_kwargs))
    h3 = activ(conv(h2, 'c3', nf=64, rf=3, stride=1, init_scale=np.sqrt(2), **conv_kwargs))
    h3 = conv_to_fc(h3)
    return activ(fc(h3, 'fc1', nh=512, init_scale=np.sqrt(2)))



@register("cnn")
def cnn(**conv_kwargs):
    def network_fn(X):
        return nature_cnn(X, **conv_kwargs)
    return network_fn

@register("lstm")
def lstm(nlstm=128,layer_norm=False):
    def network_fn(X,nenv=1):
        nbatch=X.shape[0]
        nsteps=nbatch//nenv
        h=tf.layers.flatten(X)

        M=tf.placeholder(tf.float32,[nbatch])
        S=tf.placeholder(tf.float32,[nenv,2*nlstm])

        xs=batch_to_seq(h,nenv,nsteps)
        ms=batch_to_seq(M,nenv,nsteps)


        if layer_norm:
            h5, snew = utils.lnlstm(xs, ms, S, scope='lnlstm', nh=nlstm)
        else:
            h5, snew = utils.lstm(xs, ms, S, scope='lstm', nh=nlstm)


        h=seq_to_batch(h5)

        initial_state=np.zeros(S.shape.as_list(),dtype=float)
        return h,{"S":S,"M":M,"state":snew,"initial_state":initial_state}

    return network_fn


@register("cnn_lstm")
def cnn_lstm(nlstm=128, layer_norm=False, **conv_kwargs):
    def network_fn(X, nenv=1):
        nbatch = X.shape[0]
        nsteps = nbatch // nenv

        h = nature_cnn(X, **conv_kwargs)

        M = tf.placeholder(tf.float32, [nbatch]) #mask (done t-1)
        S = tf.placeholder(tf.float32, [nenv, 2*nlstm]) #states

        xs = batch_to_seq(h, nenv, nsteps)
        ms = batch_to_seq(M, nenv, nsteps)

        if layer_norm:
            h5, snew = utils.lnlstm(xs, ms, S, scope='lnlstm', nh=nlstm)
        else:
            h5, snew = utils.lstm(xs, ms, S, scope='lstm', nh=nlstm)

        h = seq_to_batch(h5)
        initial_state = np.zeros(S.shape.as_list(), dtype=float)

        return h, {'S':S, 'M':M, 'state':snew, 'initial_state':initial_state}

    return network_fn



















def get_network_builder(name):

    if callable(name):
        return name
    elif name in mapping:
        return mapping[name]
    else:
        raise ValueError("Unknow network type:{}".format(name))


# if __name__ =="__main__":
#     a=get_network_builder("mlp")
#     print(a)
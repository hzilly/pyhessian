"""
    hessian_estimator.py - Hessian Matrix Estimator
 
    Copyright (c) 1996-2016 by Geir K. Nilsen (geir.kjetil.nilsen@gmail.com)
    and the University of Bergen.
 
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
 
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.
    
    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
import tensorflow as tf
import numpy as np

class HessianEstimator(object):
    """ Implements a Hessian matrix estimator
       
    Attributes:
        layers: Model architecture, number of neurons per layer (list of ints)
        cost_fun: Cost function (function)
        cost: Cost function output (tensor)
        model_fun: Model function (function)
        params: List of model parameters (list of tensor(s))
        p: Total number of model parameters (int)
        X: Model input (tensor)
        y: Model output (tensor)
        batch_size: Batch size used to estimate Hessian OPG approximation   
    
    """
    def __init__(self, layers, cost_fun, cost, model_fun, params, X, y, batch_size):
        """
        Args:
            layers: Model architecture, number of neurons per layer (list of ints)
            cost_fun(y, yhat_logits, params): Cost function (function)
                Args:
                    y: Labels (tensor)
                    yhat_logits: Model output in logits (tensor)
                    params: List of model parameter(s) \
                            (List of tensor(s)) [Can be used for regularization \
                                                 purposes]        
                Returns:            
                    cost: Cost function output (tensor)        
            
            cost: Cost function output (tensor)
            model_fun(x, params): Model function (function),     
                Args:
                    X: Model input (tensor)
                    params:  List of model parameter(s) \
                             (List of tensor(s))
         
                Returns:
                    y: Model output (tensor)                     
            params: List of model parameters (list of tensor(s))
            X: Model input (tensor)
            y: Model output (tensor)
            batch_size: Batch size used to estimate Hessian OPG approximation (
                        int)
        """
        self.layers = layers
        self.cost_fun = cost_fun
        self.cost = cost
        self.model_fun = model_fun
        self.params = params
        self.P = np.sum([layers[l]*layers[l+1]+layers[l+1] 
                         for l in range(len(layers)-1)])
        self.X = X
        self.y = y
        self.batch_size = batch_size

    def flatten(self, params):
        """
        Flattens the list of tensor(s) into a 1D tensor
        
        Args:
            params: List of model parameters (List of tensor(s))
        
        Returns:
            A flattened 1D tensor
        """
        weights = tf.concat([tf.reshape(params[l], 
                                        shape=(self.layers[l]*self.layers[l+1],)) 
                             for l in range(len(self.layers)-1)],axis=0)
        biases = tf.concat([params[l+len(self.layers)-1] 
                            for l in range(len(self.layers)-1)],axis=0)        
        params_flat = tf.concat([weights, biases], axis=0)
        return params_flat

    def flatten_v2(self, params):
        return tf.concat([tf.reshape(params[l], [-1]) for l in range(len(self.layers))], axis=0)

    def unflatten(self, params_flat):
        """
        Unflattens the 1D tensor into a list of tensors. Inverse of flatten(params), \
        e.g. unflatten(flatten(params)) = params.
        
        Args:
            params_flat: The model parameters as a flat 1D tensor
            
        Returns:
            params: A list of model parameters (List of tensor(s))
        """
        winds = np.cumsum(np.concatenate([[0], 
                          np.multiply(np.roll(self.layers,-1)[:-1], 
                                              self.layers[:-1])]))
        weights = [tf.reshape(params_flat[winds[l]:winds[l+1]], 
                              shape=(self.layers[l],
                                     self.layers[l+1])) 
                   for l in range(len(self.layers)-1)]
        binds = np.concatenate([[winds[-1]], winds[-1]+ \
                                             np.cumsum(self.layers[1:])])
        biases = [tf.reshape(params_flat[binds[l]:binds[l+1]], 
                             shape=(self.layers[l+1],)) 
                  for l in range(len(self.layers)-1)]
        return weights+biases


    def get_Hv_op(self, v):
        """ 
        Implements a Hessian vector product estimator Hv op defined as the matrix \
        multiplication of the Hessian matrix H with the vector v.
    
        Args:      
            v: Vector to multiply with Hessian (tensor)
        
        Returns:
            Hv_op: Hessian vector product op (tensor)
        """
        cost_gradient = self.flatten(tf.gradients(self.cost, 
                                                  self.params))
        vprod = tf.math.multiply(cost_gradient, 
                                 tf.stop_gradient(v))
        Hv_op = self.flatten(tf.gradients(vprod, 
                                          self.params))
        return Hv_op

    def get_H_op(self):
        """ 
        Implements a full Hessian estimator op by forming p Hessian vector products \
        using HessianEstimator.get_Hv_op(v) for all v's in R^p
        
        Args:
            None
        
        Returns:
            H_op: Hessian matrix op (tensor)
        """
        H_op = tf.map_fn(self.get_Hv_op, tf.eye(self.P, 
                                                self.P), 
                         dtype='float32')
        return H_op
    
    def get_G_op(self):
        """ 
        Implements a Hessian matrix OPG approximation op by a per-example cost
        Jacobian matrix product
     
        Args:
            None
        
        Returns:
            G_op: Hessian matrix OPG approximation op (tensor)
        """
        """
        ex_params_flat = [tf.identity(self.flatten(self.params)) \
                          for ex in range(self.batch_size)]
        ex_params = [self.unflatten(ex_params_flat[ex]) \
                     for ex in range(self.batch_size)]
        """                
        ex_params = [[tf.identity(self.params[l]) \
                      for l in range(len(self.layers))] \
                     for ex in range(self.batch_size)]      
        
        ex_X = tf.split(self.X, self.batch_size)
        ex_y = tf.split(self.y, self.batch_size)    
        ex_yhat_logits = [self.model_fun(_X, _params) \
                          for _X, _params in zip(ex_X, 
                                                 ex_params)]
        ex_cost = [self.cost_fun(_y, _yhat_logits, _params) \
                   for _y, _yhat_logits, _params in zip(ex_y, 
                                                        ex_yhat_logits,
                                                        ex_params)]
        ex_grads = tf.stack([self.flatten(tf.gradients(ex_cost[ex],
                                                       ex_params[ex])) \
                             for ex in range(self.batch_size)])
        G_op = tf.matmul(tf.transpose(ex_grads), 
                         ex_grads) / self.batch_size
        return G_op
                     
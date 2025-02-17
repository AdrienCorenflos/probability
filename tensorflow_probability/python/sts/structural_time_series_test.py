# Copyright 2018 The TensorFlow Probability Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ============================================================================
"""Tests for tensorflow_probability.python.sts.structural_time_series."""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import tensorflow.compat.v1 as tf1
import tensorflow.compat.v2 as tf
import tensorflow_probability as tfp
from tensorflow_probability.python import distributions as tfd
from tensorflow_probability.python.internal import samplers
from tensorflow_probability.python.internal import test_util
from tensorflow_probability.python.sts import Autoregressive
from tensorflow_probability.python.sts import DynamicLinearRegression
from tensorflow_probability.python.sts import LinearRegression
from tensorflow_probability.python.sts import LocalLevel
from tensorflow_probability.python.sts import LocalLinearTrend
from tensorflow_probability.python.sts import Seasonal
from tensorflow_probability.python.sts import SemiLocalLinearTrend
from tensorflow_probability.python.sts import SmoothSeasonal
from tensorflow_probability.python.sts import SparseLinearRegression
from tensorflow_probability.python.sts import Sum
from tensorflow_probability.python.sts.internal import util as sts_util


class _StructuralTimeSeriesTests(object):

  def test_broadcast_batch_shapes(self):

    batch_shape = [3, 1, 4]
    partial_batch_shape = [2, 1]
    expected_broadcast_batch_shape = [3, 2, 4]

    # Build a model where parameters have different batch shapes.
    partial_batch_loc = self._build_placeholder(
        np.random.randn(*partial_batch_shape))
    full_batch_loc = self._build_placeholder(
        np.random.randn(*batch_shape))

    partial_scale_prior = tfd.LogNormal(
        loc=partial_batch_loc, scale=tf.ones_like(partial_batch_loc))
    full_scale_prior = tfd.LogNormal(
        loc=full_batch_loc, scale=tf.ones_like(full_batch_loc))
    loc_prior = tfd.Normal(loc=partial_batch_loc,
                           scale=tf.ones_like(partial_batch_loc))

    linear_trend = LocalLinearTrend(level_scale_prior=full_scale_prior,
                                    slope_scale_prior=full_scale_prior,
                                    initial_level_prior=loc_prior,
                                    initial_slope_prior=loc_prior)
    seasonal = Seasonal(num_seasons=3,
                        drift_scale_prior=partial_scale_prior,
                        initial_effect_prior=loc_prior)
    model = Sum([linear_trend, seasonal],
                observation_noise_scale_prior=partial_scale_prior)
    param_samples = [p.prior.sample() for p in model.parameters]
    ssm = model.make_state_space_model(num_timesteps=2,
                                       param_vals=param_samples)

    # Test that the model's batch shape matches the SSM's batch shape,
    # and that they both match the expected broadcast shape.
    self.assertAllEqual(model.batch_shape, ssm.batch_shape)

    (model_batch_shape_tensor_,
     ssm_batch_shape_tensor_) = self.evaluate((model.batch_shape_tensor(),
                                               ssm.batch_shape_tensor()))
    self.assertAllEqual(model_batch_shape_tensor_, ssm_batch_shape_tensor_)
    self.assertAllEqual(model_batch_shape_tensor_,
                        expected_broadcast_batch_shape)

  def test_addition_raises_error_with_no_observed_time_series(self):
    c1 = tfp.sts.LocalLevel(level_scale_prior=tfd.Normal(0., 1.),
                            initial_level_prior=tfd.Normal(0., 1.))
    c2 = tfp.sts.LocalLevel(level_scale_prior=tfd.Normal(0., 0.1),
                            initial_level_prior=tfd.Normal(1., 2.))
    with self.assertRaisesRegex(
        ValueError, 'Could not automatically create a `Sum` component'):
      c1 + c2  # pylint: disable=pointless-statement

  def test_adding_two_sums(self):
    observed_time_series = self._build_placeholder([1., 2., 3., 4., 5.])
    s1 = tfp.sts.Sum(
        [tfp.sts.LocalLevel(observed_time_series=observed_time_series)],
        observed_time_series=observed_time_series)
    s2 = tfp.sts.Sum(
        [tfp.sts.LocalLinearTrend(observed_time_series=observed_time_series)],
        observed_time_series=observed_time_series)
    s3 = s1 + s2
    self.assertLen(s3.components, 2)

    observation_noise_scale_prior_sample = (
        lambda s: s.parameters[0].prior.sample(  # pylint: disable=g-long-lambda
            seed=test_util.test_seed(sampler_type='stateless')))
    self.assertAllEqual(observation_noise_scale_prior_sample(s3),
                        observation_noise_scale_prior_sample(s1))
    self.assertAllEqual(observation_noise_scale_prior_sample(s3),
                        observation_noise_scale_prior_sample(s2))

    self.assertAllEqual(s3.constant_offset, s1.constant_offset)
    self.assertAllEqual(s3.constant_offset, s2.constant_offset)

    with self.assertRaisesRegex(
        ValueError, 'Cannot add Sum components'):
      s1.copy(observed_time_series=3 * observed_time_series) + s2  # pylint: disable=expression-not-assigned

    with self.assertRaisesRegex(
        ValueError, 'Cannot add Sum components'):
      s1.copy(constant_offset=4.) + s2  # pylint: disable=expression-not-assigned

    with self.assertRaisesRegex(
        ValueError, 'Cannot add Sum components'):
      s1.copy(observation_noise_scale_prior=tfd.Normal(  # pylint: disable=expression-not-assigned
          self._build_placeholder(0.), self._build_placeholder(1.))) + s2

  def _build_placeholder(self, ndarray, dtype=None):
    """Convert a numpy array to a TF placeholder.

    Args:
      ndarray: any object convertible to a numpy array via `np.asarray()`.
      dtype: optional `dtype`; if not specified, defaults to `self.dtype`.

    Returns:
      placeholder: a TensorFlow `placeholder` with default value given by the
      provided `ndarray`, dtype given by `self.dtype`, and shape specified
      statically only if `self.use_static_shape` is `True`.
    """

    if dtype is None:
      dtype = self.dtype

    ndarray = np.asarray(ndarray).astype(dtype)
    return tf1.placeholder_with_default(
        ndarray, shape=ndarray.shape if self.use_static_shape else None)


@test_util.test_all_tf_execution_regimes
class StructuralTimeSeriesTestsStaticShape32(
    _StructuralTimeSeriesTests, test_util.TestCase):
  dtype = np.float32
  use_static_shape = True


@test_util.test_all_tf_execution_regimes
class StructuralTimeSeriesTestsDynamicShape32(
    _StructuralTimeSeriesTests, test_util.TestCase):
  dtype = np.float32
  use_static_shape = False


@test_util.test_all_tf_execution_regimes
class StructuralTimeSeriesTestsStaticShape64(
    _StructuralTimeSeriesTests, test_util.TestCase):
  dtype = np.float64
  use_static_shape = True


class _StsTestHarness(object):

  def test_state_space_model(self):
    seed = test_util.test_seed_stream()
    model = self._build_sts()

    dummy_param_vals = [p.prior.sample(seed=seed()) for p in model.parameters]
    initial_state_prior = tfd.MultivariateNormalDiag(
        loc=-2. + tf.zeros([model.latent_size]),
        scale_diag=3. * tf.ones([model.latent_size]))

    mask = tf.convert_to_tensor(
        [False, True, True, False, False, False, False, True, False, False],
        dtype=tf.bool)

    # Verify we build the LGSSM without errors.
    ssm = model.make_state_space_model(
        num_timesteps=10,
        param_vals=dummy_param_vals,
        initial_state_prior=initial_state_prior,
        initial_step=1,
        mask=mask)

    # Verify that the child class passes the initial step, prior, and mask
    # arguments through to the SSM.
    self.assertEqual(self.evaluate(ssm.initial_step), 1)
    self.assertEqual(ssm.initial_state_prior, initial_state_prior)
    self.assertAllEqual(ssm.mask, mask)

    # Verify the model has the correct latent size.
    self.assertEqual(
        self.evaluate(
            tf.convert_to_tensor(
                ssm.latent_size_tensor())),
        model.latent_size)

    # Verify that the SSM tracks its parameters.
    observed_time_series = self.evaluate(
        samplers.normal([10, 1], seed=test_util.test_seed()))
    ssm_copy = ssm.copy(name='copied_ssm')
    self.assertAllClose(*self.evaluate((
        ssm.log_prob(observed_time_series),
        ssm_copy.log_prob(observed_time_series))))

  def test_log_joint(self):
    seed = test_util.test_seed_stream()
    model = self._build_sts()
    num_timesteps = 5

    # simple case: single observation, and all params unbatched
    log_joint_fn = model.joint_log_prob(
        observed_time_series=np.float32(
            np.random.standard_normal([num_timesteps, 1])))
    lp = self.evaluate(
        log_joint_fn(*[p.prior.sample(seed=seed()) for p in model.parameters]))
    self.assertEqual(tf.TensorShape([]), lp.shape)

    # more complex case: y has sample and batch shapes, some parameters
    # have partial batch shape.
    full_batch_shape = [2, 3]
    partial_batch_shape = [3]
    sample_shape = [4]
    log_joint_fn = model.joint_log_prob(
        observed_time_series=np.float32(
            np.random.standard_normal(sample_shape + full_batch_shape +
                                      [num_timesteps, 1])))

    # We alternate full_batch_shape, partial_batch_shape in sequence so that in
    # a model with only one parameter, that parameter is constructed with full
    # batch shape.
    batch_shaped_parameters_ = self.evaluate([
        p.prior.sample(sample_shape=full_batch_shape if (i % 2 == 0)
                       else partial_batch_shape, seed=seed())
        for (i, p) in enumerate(model.parameters)])

    lp = self.evaluate(log_joint_fn(*batch_shaped_parameters_))
    self.assertEqual(tf.TensorShape(full_batch_shape), lp.shape)

    # Check that the log joint function also supports parameters passed
    # as kwargs.
    parameters_by_name_ = {
        p.name: v for (p, v) in zip(model.parameters, batch_shaped_parameters_)}
    lp_with_kwargs = self.evaluate(log_joint_fn(**parameters_by_name_))
    self.assertAllClose(lp, lp_with_kwargs)

  def test_constant_series_does_not_induce_constant_prior(self):
    observed_time_series = np.array([1.0, 1.0, 1.0]).astype(np.float32)
    model = self._build_sts(observed_time_series=observed_time_series)
    for parameter in model.parameters:
      param_samples = self.evaluate(
          parameter.prior.sample(30, seed=test_util.test_seed()))
      self.assertAllGreater(tf.math.reduce_std(param_samples), 0.)

  def test_log_joint_with_missing_observations(self):
    # Test that this component accepts MaskedTimeSeries inputs. In most
    # cases, it is sufficient that the component accesses only
    # `empirical_statistics(observed_time_series)`.
    # TODO(b/139483802): De-flake this test when run with --vary_seed.
    seed = test_util.test_seed_stream(hardcoded_seed=123)
    observed_time_series = np.array(
        [1.0, 2.0, -1000., 0.4, np.nan, 1000., 4.2, np.inf]).astype(np.float32)
    observation_mask = np.array(
        [False, False, True, False, True, True, False, True]).astype(np.bool_)
    masked_time_series = tfp.sts.MaskedTimeSeries(observed_time_series,
                                                  is_missing=observation_mask)

    model = self._build_sts(observed_time_series=masked_time_series)

    log_joint_fn = model.joint_log_prob(
        observed_time_series=masked_time_series)
    lp = self.evaluate(
        log_joint_fn(*[p.prior.sample(seed=seed()) for p in model.parameters]))

    self.assertEqual(tf.TensorShape([]), lp.shape)
    self.assertTrue(np.isfinite(lp))

  def test_prior_sample(self):
    model = self._build_sts()
    ys, param_samples = model.prior_sample(
        num_timesteps=5, params_sample_shape=[2], trajectories_sample_shape=[3],
        seed=test_util.test_seed())

    self.assertAllEqual(ys.shape, [3, 2, 5, 1])
    self.assertEqual(len(param_samples), len(model.parameters))
    for i in range(len(param_samples)):
      sampled = param_samples[i]
      param = model.parameters[i]
      self.assertAllEqual(sampled.shape, [
          2,
      ] + param.prior.batch_shape.as_list() + param.prior.event_shape.as_list())

  def test_joint_distribution_log_prob(self):
    model = self._build_sts()
    jd = model.joint_distribution(trajectories_shape=[2], num_timesteps=11)
    self.assertLen(jd.dtype, len(model.parameters) + 1)

    # Time series sampled from the JD should have the expected shape.
    samples = self.evaluate(
        jd.sample(seed=test_util.test_seed(sampler_type='stateless')))
    observed_time_series = samples['observed_time_series']
    self.assertAllEqual(tf.shape(observed_time_series),
                        tf.concat([model.batch_shape_tensor(), [2, 11, 1]],
                                  axis=0))

    # The JD's `log_prob` val should match the previous `joint_log_prob` method.
    sampled_params = list(samples.values())[:-1]
    lp0 = model.joint_log_prob(observed_time_series)(*sampled_params)
    lp1 = jd.log_prob(samples)
    self.assertAllClose(lp0, lp1)

    # Passing `observed_time_series` should return the pinned distribution.
    jd_pinned = model.joint_distribution(
        observed_time_series=observed_time_series)
    lp2 = jd_pinned.unnormalized_log_prob(*sampled_params)
    self.assertAllClose(lp0, lp2)

    # The JD should expose the STS bijectors as its default bijectors.
    jd_bijectors = jd._model_unflatten(
        jd.experimental_default_event_space_bijector().bijectors)
    for param in model.parameters:
      self.assertEqual(param.bijector, jd_bijectors[param.name])

  def test_default_priors_follow_batch_shapes(self):
    seed = test_util.test_seed_stream()
    num_timesteps = 3
    time_series_sample_shape = [4, 2]
    observation_shape_full = time_series_sample_shape + [num_timesteps]
    dummy_observation = np.random.randn(
        *(observation_shape_full)).astype(np.float32)

    model = self._build_sts(observed_time_series=dummy_observation)

    # The model should construct a default parameter prior for *each* observed
    # time series, so the priors will have batch_shape equal to
    # `time_series_sample_shape`.
    for parameter in model.parameters:
      self.assertEqual(parameter.prior.batch_shape, time_series_sample_shape)

    # The initial state prior should also have the appropriate batch shape.
    # To test this, we build the ssm and test that it has a consistent
    # broadcast batch shape.
    param_samples = [p.prior.sample(seed=seed()) for p in model.parameters]
    ssm = model.make_state_space_model(
        num_timesteps=num_timesteps, param_vals=param_samples)
    self.assertEqual(ssm.batch_shape, time_series_sample_shape)

  def test_copy(self):
    model = self._build_sts()
    copy = model.copy()
    self.assertNotEqual(id(model), id(copy))
    self.assertAllEqual([p.name for p in model.parameters],
                        [p.name for p in copy.parameters])

  def test_add_component(self):
    model = self._build_sts(observed_time_series=[1., 2., 3.])
    new_component = tfp.sts.LocalLevel(name='LocalLevel2')
    sum_model = model + new_component
    ledom_mus = new_component + model  # `sum_model` backwards.
    self.assertIsInstance(sum_model, tfp.sts.Sum)
    self.assertIsInstance(ledom_mus, tfp.sts.Sum)
    self.assertEqual(sum_model.components[-1], new_component)
    self.assertEqual(ledom_mus.components[0], new_component)
    self.assertEqual(set([p.name for p in sum_model.parameters]),
                     set([p.name for p in ledom_mus.parameters]))
    # If we built a new Sum component (rather than extending an existing one),
    # we should have passed an observed_time_series so that we get reasonable
    # default priors.
    if not isinstance(model, tfp.sts.Sum):
      self.assertIsNotNone(sum_model.init_parameters['observed_time_series'])
      self.assertIsNotNone(ledom_mus.init_parameters['observed_time_series'])


@test_util.test_all_tf_execution_regimes
class AutoregressiveTest(test_util.TestCase, _StsTestHarness):

  def _build_sts(self, observed_time_series=None):
    return Autoregressive(order=3, observed_time_series=observed_time_series)


@test_util.test_all_tf_execution_regimes
class LocalLevelTest(test_util.TestCase, _StsTestHarness):

  def _build_sts(self, observed_time_series=None):
    return LocalLevel(observed_time_series=observed_time_series)


@test_util.test_all_tf_execution_regimes
class LocalLinearTrendTest(test_util.TestCase, _StsTestHarness):

  def _build_sts(self, observed_time_series=None):
    return LocalLinearTrend(observed_time_series=observed_time_series)


@test_util.test_all_tf_execution_regimes
class SeasonalTest(test_util.TestCase, _StsTestHarness):

  def _build_sts(self, observed_time_series=None):
    # Note that a Seasonal model with `num_steps_per_season > 1` would have
    # deterministic dependence between timesteps, so evaluating `log_prob` of an
    # arbitrary time series leads to Cholesky decomposition errors unless the
    # model also includes an observation noise component (which it would in
    # practice, but this test harness attempts to test the component in
    # isolation). The `num_steps_per_season=1` case tested here will not suffer
    # from this issue.
    return Seasonal(num_seasons=7,
                    num_steps_per_season=1,
                    observed_time_series=observed_time_series,
                    constrain_mean_effect_to_zero=False)


@test_util.test_all_tf_execution_regimes
class SeasonalWithZeroMeanConstraintTest(test_util.TestCase, _StsTestHarness):

  def _build_sts(self, observed_time_series=None):
    return Seasonal(num_seasons=7,
                    num_steps_per_season=1,
                    observed_time_series=observed_time_series,
                    constrain_mean_effect_to_zero=True)


@test_util.test_all_tf_execution_regimes
class SeasonalWithMultipleStepsAndNoiseTest(test_util.TestCase,
                                            _StsTestHarness):

  def _build_sts(self, observed_time_series=None):
    day_of_week = tfp.sts.Seasonal(num_seasons=7,
                                   num_steps_per_season=24,
                                   allow_drift=False,
                                   observed_time_series=observed_time_series,
                                   name='day_of_week')
    return tfp.sts.Sum(components=[day_of_week],
                       observed_time_series=observed_time_series)


@test_util.test_all_tf_execution_regimes
class SemiLocalLinearTrendTest(test_util.TestCase, _StsTestHarness):

  def _build_sts(self, observed_time_series=None):
    return SemiLocalLinearTrend(observed_time_series=observed_time_series)


@test_util.test_all_tf_execution_regimes
class SmoothSeasonalTest(test_util.TestCase, _StsTestHarness):

  def _build_sts(self, observed_time_series=None):
    return SmoothSeasonal(period=42,
                          frequency_multipliers=[1, 2, 4],
                          observed_time_series=observed_time_series)


@test_util.test_all_tf_execution_regimes
class SmoothSeasonalWithNoDriftTest(test_util.TestCase, _StsTestHarness):

  def _build_sts(self, observed_time_series=None):
    smooth_seasonal = SmoothSeasonal(period=42,
                                     frequency_multipliers=[1, 2, 4],
                                     allow_drift=False,
                                     observed_time_series=observed_time_series)
    # The test harness doesn't like models with no parameters, so wrap with Sum.
    return tfp.sts.Sum([smooth_seasonal],
                       observed_time_series=observed_time_series)


@test_util.test_all_tf_execution_regimes
class SumTest(test_util.TestCase, _StsTestHarness):

  def _build_sts(self, observed_time_series=None):
    first_component = LocalLinearTrend(
        observed_time_series=observed_time_series, name='first_component')
    second_component = LocalLinearTrend(
        observed_time_series=observed_time_series, name='second_component')
    return Sum(
        components=[first_component, second_component],
        observed_time_series=observed_time_series)


@test_util.test_all_tf_execution_regimes
class LinearRegressionTest(test_util.TestCase, _StsTestHarness):

  def _build_sts(self, observed_time_series=None):
    max_timesteps = 100
    num_features = 3

    prior = tfd.Sample(tfd.Laplace(0., 1.), sample_shape=[num_features])

    # LinearRegression components don't currently take an `observed_time_series`
    # argument, so they can't infer a prior batch shape. This means we have to
    # manually set the batch shape expected by the tests.
    if observed_time_series is not None:
      observed_time_series_tensor, _ = (
          sts_util.canonicalize_observed_time_series_with_mask(
              observed_time_series))
      batch_shape = tf.shape(observed_time_series_tensor)[:-2]
      prior = tfd.Sample(tfd.Laplace(tf.zeros(batch_shape), 1.),
                         sample_shape=[num_features])

    regression = LinearRegression(
        design_matrix=np.random.randn(
            max_timesteps, num_features).astype(np.float32),
        weights_prior=prior)
    return Sum(components=[regression],
               observed_time_series=observed_time_series)


@test_util.test_all_tf_execution_regimes
class SparseLinearRegressionTest(test_util.TestCase, _StsTestHarness):

  def _build_sts(self, observed_time_series=None):
    max_timesteps = 100
    num_features = 3

    # LinearRegression components don't currently take an `observed_time_series`
    # argument, so they can't infer a prior batch shape. This means we have to
    # manually set the batch shape expected by the tests.
    batch_shape = None
    if observed_time_series is not None:
      observed_time_series_tensor, _ = (
          sts_util.canonicalize_observed_time_series_with_mask(
              observed_time_series))
      batch_shape = tf.shape(observed_time_series_tensor)[:-2]

    regression = SparseLinearRegression(
        design_matrix=np.random.randn(
            max_timesteps, num_features).astype(np.float32),
        weights_batch_shape=batch_shape)
    return Sum(components=[regression],
               observed_time_series=observed_time_series)


@test_util.test_all_tf_execution_regimes
class DynamicLinearRegressionTest(test_util.TestCase, _StsTestHarness):

  def _build_sts(self, observed_time_series=None):
    max_timesteps = 100
    num_features = 3

    return DynamicLinearRegression(
        design_matrix=np.random.randn(
            max_timesteps, num_features).astype(np.float32),
        observed_time_series=observed_time_series)


if __name__ == '__main__':
  test_util.main()

# Copyright 2021 The TensorFlow Probability Authors.
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
# [internal] load pytype.bzl (pytype_strict_library)
# [internal] load strict.bzl

licenses(["notice"])

package(default_visibility = ["//visibility:public"])

# pytype_strict
py_library(
    name = "einsum",
    srcs = ["einsum.py"],
    srcs_version = "PY3",
    deps = [
        # jax dep,
        "//oryx/experimental/matching:jax_rewrite",
        "//oryx/experimental/matching:matcher",
    ],
)

# pytype_strict
py_library(
    name = "canonicalize",
    srcs = ["canonicalize.py"],
    srcs_version = "PY3",
    deps = [
        ":einsum",
        # jax dep,
        "//oryx/experimental/matching:jax_rewrite",
        "//oryx/experimental/matching:matcher",
        "//oryx/experimental/matching:rules",
    ],
)

# py_strict
py_test(
    name = "einsum_test",
    srcs = ["einsum_test.py"],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":einsum",
        # absl/testing:absltest dep,
        # jax dep,
        # numpy dep,
        "//oryx/experimental/matching:jax_rewrite",
        "//oryx/experimental/matching:matcher",
        "//oryx/experimental/matching:rules",
        "//oryx/internal:test_util",
    ],
)

# py_strict
py_test(
    name = "canonicalize_test",
    srcs = ["canonicalize_test.py"],
    python_version = "PY3",
    srcs_version = "PY3",
    deps = [
        ":canonicalize",
        ":einsum",
        # absl/testing:absltest dep,
        # jax dep,
        # numpy dep,
        "//oryx/experimental/matching:jax_rewrite",
        "//oryx/internal:test_util",
    ],
)

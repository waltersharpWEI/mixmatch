#!/usr/bin/env bash

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

echo "# CIFAR10 hyper-parameters for all methods under comparison"
for timeb in 60 600 1200 2400; do
echo "##Time Budget $timeb ##"
for seed in 1; do
for size in 4000; do
for sigma in 1 4 8 16 32 64 128 256; do
    common_args="--train_dir experiments/compare --dataset=cifar10.${seed}@${size}-1"
    python distil3.py $common_args --wd=0.02 --smoothing=0.01 --consistency_weight=1 --sigma=$sigma --time_budget=$timeb
done
done
done
done

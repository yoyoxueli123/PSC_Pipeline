#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import print_function

import argparse
from distutils.version import LooseVersion
import json
import os

import nibabel as nib
if LooseVersion(nib.__version__) < LooseVersion('2.1.0'):
    raise ImportError("Unable to import the Nibabel streamline API. "
                      "Nibabel >= v2.1.0 is required")
import numpy as np

from scilpy.io.image import assert_same_resolution
from scilpy.io.utils import assert_inputs_exist
from scilpy.tracking.tools import subsample_streamlines
from scilpy.utils.filenames import split_name_with_nii
from scilpy.utils.metrics_tools import get_metrics_profile_over_streamlines
from scilpy.utils.streamlines import load_in_voxel_space


def norm_l2(x):
    return np.sqrt(np.sum(np.power(x, 2), axis=1, dtype="float"))


def average_euclidean(x, y):
    return np.mean(norm_l2(x - y))


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description='Compute tract profiles and their statistics along '
                    'streamlines',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        'bundle',
        help='Fiber bundle file to compute the tract profiles on')
    parser.add_argument(
        'metrics', nargs='+',
        help='Nifti metric(s) on which to compute the tract profiles')
    parser.add_argument(
        '--num_points', type=int, default=20,
        help='Subsample each streamline to this number of points')
    parser.add_argument('--indent', type=int, default=2,
                        help='Indent for json pretty print')
    parser.add_argument('--sort_keys', action='store_true',
                        help='Sort keys in output json')
    return parser


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    assert_inputs_exist(parser, [args.bundle] + args.metrics)
    if args.num_points <= 1:
        parser.error('--num_points {} needs to be greater than '
                     '1'.format(args.num_points))

    metrics = [nib.load(m) for m in args.metrics]
    assert_same_resolution(*metrics)

    bundle_tractogram_file = nib.streamlines.load(args.bundle)

    bundle_name, _ = os.path.splitext(os.path.basename(args.bundle))
    stats = {}
    if len(bundle_tractogram_file.streamlines) == 0:
        stats[bundle_name] = None
        print(json.dumps(stats, indent=args.indent, sort_keys=args.sort_keys))
        return

    bundle_streamlines_vox = load_in_voxel_space(
        bundle_tractogram_file, metrics[0])
    bundle_subsampled = subsample_streamlines(
        bundle_streamlines_vox,
        num_points=args.num_points,
        arc_length=True)

    # Make sure all streamlines go in the same direction. We want to make
    # sure point #1 / 20 of streamline A is matched with point #1 / 20 of
    # streamline B and so on
    num_streamlines = len(bundle_subsampled)
    reference = bundle_subsampled[0]
    for s in np.arange(num_streamlines):
        streamline = bundle_subsampled[s]
        direct = average_euclidean(reference, streamline)
        flipped = average_euclidean(reference, streamline[::-1])

        if flipped < direct:
            bundle_subsampled[s] = streamline[::-1]

    profiles = get_metrics_profile_over_streamlines(bundle_subsampled,
                                                    metrics)
    t_profiles = np.expand_dims(profiles, axis=1)
    t_profiles = np.rollaxis(t_profiles, 3, 2)

    stats[bundle_name] = {}
    for metric, profile, t_profile in zip(metrics, profiles, t_profiles):
        metric_name, _ = split_name_with_nii(
            os.path.basename(metric.get_filename()))
        stats[bundle_name][metric_name] = {
            'mean': np.mean(profile, axis=0).tolist(),
            'std': np.std(profile, axis=0).tolist(),
            'tractprofile': t_profile.tolist()
        }

    print(json.dumps(stats, indent=args.indent, sort_keys=args.sort_keys))


if __name__ == '__main__':
    main()

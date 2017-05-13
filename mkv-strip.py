#!/usr/bin/python

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4

from collections import OrderedDict
from hashlib import md5
from io import StringIO
from os.path import isfile, join
from tabulate import tabulate

import argparse
import logging
import os
import re
import subprocess
import sys


parser = argparse.ArgumentParser(
    description='Strip MKV files to a single language')
parser.add_argument(
    '--input-directory',
    help='Directory with source MKV files to be processed',
    required=True,
)
parser.add_argument(
    '--audio-language',
    help='Audio language to keep. All other audio languages will be stripped',
)
parser.add_argument(
    '--subtitle-language',
    help='Subtitle language to keep. All other subtitle languages will be stripped',
    required=False,
)
parser.add_argument(
    '--list-tracks',
    help='List tracks in the files in the input directory',
    action='store_true'
)

args = parser.parse_args()
logging.basicConfig(format='%(asctime)s %(message)s')
logger = logging.getLogger('converter')
file_to_tracks = {}

# set this to the path for mkvmerge
MKVMERGE = "C:/Program Files/MKVtoolnix/mkvmerge.exe"

AUDIO_RE = re.compile(r"Track ID (\d+): audio .*language:([a-z]{3})")
SUBTITLE_RE = re.compile(r"Track ID (\d+): subtitles .*language:([a-z]{3})")


def _get_file_list(root=None):
    logger.critical(f'Processing {root}')
    dir_contents = os.listdir(root)
    paths = [f for f in dir_contents 
                if isfile(join(root, f)) and f.endswith('.mkv')]
    return paths


def _mkvmerge_identify(root=None, filename=None):
    logger.critical(f'[{filename}] Identifying')
    cmd = [MKVMERGE, "--identify-verbose", join(root, filename)]
    mkvmerge = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = mkvmerge.communicate()
    if mkvmerge.returncode != 0:
        logger.critical(
            f'[{filename}] mkvmerge failed to identify the file')
        raise Exception(stdout.decode('utf-8'))
    return stdout.decode('utf-8')


def _extract_tracks(mkvmerge_output=None, filename=None):
    logger.critical(f'[{filename}] Extracting tracks')
    audio = []
    subtitle = []

    for line in StringIO(content):
        m = AUDIO_RE.match(line)
        if m:
            audio.append(m.groups())
        else:
            m = SUBTITLE_RE.match(line)
            if m:
                subtitle.append(m.groups())
    logger.critical(
        f'[{filename}] Found {len(audio)} audio and '
        f'{len(subtitle)} subtitle tracks'
    )
    return audio, subtitle


def _list_tracks(file_tracks=None):
    for key, rec in file_tracks.items():
        print('f{rec.filename}')
        print(' Audio tracks')
        if rec.audio:
            for t in rec.audio:
                print('  {} is {}'.format(t[0], t[1]))
        if rec.subtitle:
            for t in rec.subtitle:
                print('  {} is {}'.format(t[0], t[1]))
        print("")


def _audio_check(file_tracks=None):
    for key, rec in file_tracks.items():
        if len(rec.audio) < 2:
            logger.critical(
                f'[{rec.filename}] At least 1 audio track required'
            )
            del file_tracks[key]
    return file_tracks
    

def _subtitle_check(file_tracks=None):
    for key, rec in file_tracks.items():
        if len(rec.subtitle) < 2:
            logger.critical(
                f'[{rec.filename}] At least 1 subtitle track required'
            )
            del file_tracks[key]
    return file_tracks


def _build_args(langtype=None):
    if langtype not in ['audio', 'subtitle']:
        Exception('Type must be audio or subtitle')

    for key, rec in file_to_tracks.items():
        logger.critical(
            f'[{rec.filename}] Building CLI arguments for {langtype} tracks'
        )
        if 'audio' in langtype:
            lang = args.audio_language
            field = rec.audio
        if 'language' in langtype:
            lang = args.audio_language
            field = rec.audio
        cmd = []
        filterlang = list(filter(lambda a: a[1]==lang, field))
        if lang and len(filterlang) == 0:
            logger.critical(
                f'[{rec.filename}] No {langtype} tracks with '
                f'language {lang} in {path}'
            )
            continue
        if len(filterlang) > 1:
            logger.critical(
                f'[{rec.filename}] More than one {langtype} track '
                f'matching {lang}. Skipping'
            )
            continue
        if len(filterlang):
            cmd = [f'--{langtype}-tracks',
                    ",".join([str(a[0]) for a in filterlang])]
            for i in range(len(filterlang)):
                cmd += ["--default-track"]
                cmd += [":".join([filterlang[i][0], "0" if i else "1"])]
        if 'audio' in langtype:
            rec.audio_args = cmd
        if 'audio' in langtype:
            rec.subtitle_args = cmd
        file_to_tracks[key] = rec


class MKVFile:
    filename = None
    audio = None
    subtitle = None
    root = None
    audio_args = []
    subtitle_args = []

    def __init__(self, root=None, filename=None, audio=None, subtitle=None):
        self.filename = filename
        self.audio = audio
        self.subtitle = subtitle
        self.root = root

    def __repr__(self):
        return f'{self.filename} {self.audio_args} {self.subtitle_args}'


files = _get_file_list(root=args.input_directory)
for filename in files:
    content = _mkvmerge_identify(
        root=args.input_directory, filename=filename)
    audio_tracks, subtitle_tracks = _extract_tracks(
        mkvmerge_output=content, filename=filename)
    file_to_tracks[md5(filename.encode()).hexdigest()] = MKVFile(
        root=args.input_directory,
        filename=filename, 
        audio=audio_tracks, 
        subtitle=subtitle_tracks)

if args.list_tracks:
    _list_tracks(file_tracks=file_to_tracks)

if args.audio_language:
    file_to_tracks = _audio_check(file_tracks=file_to_tracks)

if args.subtitle_language:
    file_to_tracks = _subtitle_check(file_tracks=file_to_tracks)

if args.audio_language:
    _build_args('audio')
        
if args.subtitle_language:
    _build_args('subtitle')

for key, rec in file_to_tracks.items():
    if not rec.audio_args and not rec.subtitle_args:
        logger.critical(f'[{rec.filename}] No work to be done')
        continue

    path = join(rec.root, rec.filename)
    old_file = 'old' + rec.filename
    cmd = [MKVMERGE, "-o", path + ".temp"]
    cmd += rec.audio_args
    cmd += rec.subtitle_args
    cmd += [path]
    logger.critical(f'[{rec.filename}] Processing ...')

    mkvmerge = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = mkvmerge.communicate()
    if mkvmerge.returncode != 0:
        logger.critical('Failed')
        raise Exception(stdout)

    logger.critical('Success')

    os.rename(path, join(rec.root, old_file))
    os.rename(path + ".temp", path)

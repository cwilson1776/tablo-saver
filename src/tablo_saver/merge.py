"""
Module for rescuing a single recording from a Tablo external drive.

This module implements functions necessary to merge a set of .ts files
found on a Tablo external drive, and create a single merged .mp4 file
with their contents. Implementation derived from:
- extract_videos_from_tablo_hard_drive.py by Ken Clifton
- https://kenclifton.com
- https://github.com/ken-clifton/tablo_videos_from_harddrive/tree/main
- https://community.tablotv.com/t/extracting-videos-from-tablo-external-hard-drive/25737/2  # noqa: E501
"""
import json
import os
import pathlib
import subprocess  # noqa: S404
import tempfile
from typing import Literal

from loguru import logger


def probe(video_file_path: pathlib.Path) -> 'json':
    """
    Returns ffprobe results in JSON format.

    @video_file_path : The absolute (full) path of the video file, string.
    """
    if not video_file_path or not video_file_path.exists():
        raise TypeError('Give ffprobe a full file path of the video')

    command = [
        'ffprobe',
        '-loglevel',
        'quiet',
        '-print_format',
        'json',
        '-show_format',
        '-show_streams',
        video_file_path,
    ]

    pipe = subprocess.Popen(  # noqa: S603
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    out, err = pipe.communicate()
    pipe.stdout.close()
    return_code = pipe.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)

    return json.loads(out)


DURATION: Literal['duration'] = 'duration'


def get_duration(video_file_path) -> float:
    """Retrieve the duration of a video [seconds]."""
    probe_result = probe(video_file_path)

    if 'format' in probe_result:
        if DURATION in probe_result.get('format'):
            return float(probe_result.get('format').get(DURATION))

    if 'streams' in probe_result:
        # commonly stream 0 is the video
        for stream in probe_result.get('streams'):
            if DURATION in stream:
                return float(stream.get(DURATION))

    # if everything didn't happen,
    # we got here because no single 'return' in the above happen.
    raise ValueError(f'I found no {DURATION}')


def prepare_segment_list(  # noqa: WPS210
    recording_path: pathlib.Path,
) -> pathlib.Path:
    """
    Process the .ts files in recording_path to produce control file.

    :returns: the name of the ffmpeg control file
    """
    logger.info('Starting processing of .ts files, this takes a while...')

    # get list of files in directory
    sorted_file_list = [
        tsfile.name for tsfile in recording_path.iterdir() if tsfile.is_file()
    ]
    # sort the files ascending
    sorted_file_list.sort()

    # temporary text file for all pieces of video built below then
    # used with ffmpeg
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as segment_list:
        segment_list_name = pathlib.Path(segment_list.name)
        # loop through the list of sorted .ts files for the recording adding
        # them to the temp textfile
        ts_count = 0
        for filename in sorted_file_list:
            # only add files with .ts extension
            if (filename.endswith('.ts')):
                # build full .ts file path
                filename_and_path = recording_path.joinpath(filename)
                # write concat text file line
                segment_list.write(f"file '{filename_and_path}'\n")
                # get .ts file duration, but must subtract 1/2 second so no
                # skipping in video
                duration = get_duration(filename_and_path) - 0.5
                # write concat text file duration line
                segment_list.write(f'duration {duration:.1f}\n')
                ts_count = ts_count + 1
                logger.info(f'Processed file: {filename}')
        segment_list.close()

    if ts_count == 0:
        os.unlink(segment_list_name)
        raise ValueError(f'No ts segments found in {recording_path}')

    logger.info('Processing of .ts files completed successfully.')
    return segment_list_name


def execute(cmd: list[str]):
    """Execute a command but present output as it occurs."""
    popen = subprocess.Popen(  # noqa: S603
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
    )
    yield from iter(popen.stdout.readline, '')
    popen.stdout.close()
    return_code = popen.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, cmd)


def do_merge(segment_list: pathlib.Path, output_file: pathlib.Path):
    """Merge the ts segments in segment_list to the target output_file."""
    command = [
        'ffmpeg',
        '-f',
        'concat',
        '-safe',
        '0',
        '-i',
        segment_list,
        '-c',
        'copy',
        '-bsf:a',
        'aac_adtstoasc',
        '-movflags',
        '+faststart',
        '-y',
        output_file,
    ]

    # run ffmpeg command to make concatenated video
    logger.info('Starting ffmpeg processing, this can take several minutes...')
    logger.info(f'The output MP4 video file will be placed in: {output_file}')

    for line in execute(command):
        print(line, end='')

    logger.info('ffmpeg concatenation of files complete.')
    segment_list.unlink()


def process(recording_path: pathlib.Path, outfile: pathlib.Path):
    """Process a tablo recording to produce a merged output file."""
    segment_list = prepare_segment_list(recording_path)
    do_merge(segment_list, outfile)


if __name__ == '__main__':
    # Define the mount point of the tablo hard drive, ie. the long text a49a...
    # On Ubuntu right-click hard-drive icon and properties, or use Disks tool
    tablo_mountpoint = '/media/osboxes/c6b87b95-7b93-46c8-bccb-b75c9c7f0841'

    # change the following to the ID of the recording from the tablo.db
    # this is found using DB Browser and SQL query as shown in comments above
    video_folder_id = '78988'  # '191181'

    mount_path = pathlib.Path(tablo_mountpoint)

    # make the full recording path by adding /rec , /recording_id, "/segs"
    recording_path = mount_path.joinpath('rec', video_folder_id, 'segs')

    # place new video file in the user's profile home/videos folder with the id
    outfile = pathlib.Path.home().joinpath(
        'Videos',
        video_folder_id,
    ).with_suffix('.mp4')

    process(recording_path, outfile)

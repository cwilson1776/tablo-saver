"""
Module for manipulating the metadata associated with an mp4 file.

This module implements functions necessary to read/write/update
metadata within an mp4 file.
"""
import json
import pathlib
import subprocess  # noqa: S404
from dataclasses import asdict
from typing import List, Literal

import tablo_saver
from loguru import logger
from tablo_saver.db import Recording

TITLE: Literal['title'] = 'title'


def get_current_tags(video_file_path: pathlib.Path) -> dict:
    """
    Returns metadata tags detected by ffprobe as a dict.

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

    json_results = json.loads(out)
    return json_results.get('format').get('tags')


mmap_tv = {
    '-year': 'orig_air_date',             # \251day
    '-longdesc': 'long_description',      # ldes (description)
    '-description': 'short_description',  # desc (synopsis)
    '-network': 'call_sign',              # tvnn (TV network/station)
    '-episode': 'episode_number',         # tves
    '-season': 'season_number',           # tvsn
    '-album': TITLE,                      # \251alb
    '-sortalbum': TITLE,                  # soal
    '-show': TITLE,                       # tvsh
    '-sorttvshow': TITLE,                 # sosn
    '-song': 'episode_title',             # \251nam
}
mmap_movie = {
    '-year': 'orig_air_date',             # \251day
    '-longdesc': 'long_description',      # ldes (description)
    '-network': 'call_sign',              # tvnn (TV network/station)
    '-description': 'short_description',  # desc (synopsis)
    '-album': TITLE,                      # \251alb
    '-sortalbum': TITLE,                  # soal
    '-song': TITLE,                       # \251nam
    '-sortname': TITLE,                 # sonm
}


def compute_media_type(recording_info: 'Recording') -> str:
    """Episode or Show -> tvshow. Movie -> movie."""
    et = recording_info.entity_type
    if et == 'Episode':
        return 'tvshow'
    if et == 'Show':
        return 'tvshow'
    return 'Movie'


def compute_resolution_code(recording_info: 'Recording') -> int:
    """Generate the correct hdvd code (0=SD,1=720,2=1080,3=2160)."""
    res = recording_info.resolution_title
    if res == '480i':
        return 0
    if res == '720p':
        return 1
    if res in {'1080i', '1080p'}:
        return 2
    if res in {'2160i', '2160p'}:
        return 3
    return -1


def compute_sorted_epname(recording_info: 'Recording') -> str:
    """Use recording_info to generate sortable episode name."""
    sname = recording_info.title
    ename = recording_info.episode_title
    snum = int(recording_info.season_number)
    enum = int(recording_info.episode_number)
    order_tag = f's{snum:02d}e{enum:02d}'
    return f'{sname} - {order_tag} - {ename}'


def process_cast_list(cast: str) -> List[List[str]]:
    """Analyze and parse cast list data."""
    cast_result = []
    try:
        tmp_cast = json.loads(cast)
    except Exception as exc:
        logger.error(f'Error occurred processing cast list: {exc}')

    for artist in tmp_cast:
        artist_names = artist.split()
        cast_result.append(artist_names)
    return cast_result


def compute_artist(
    recording_info: 'Recording',
    for_sorting: bool,
) -> List[List[str]]:
    """Use recording_info to generate artist (cast) value."""
    if recording_info.top_cast:
        cast_data = process_cast_list(recording_info.top_cast)
    elif recording_info.full_cast:
        cast_data = process_cast_list(recording_info.full_cast)
    else:
        return ''

    cast_names = []
    for artist in cast_data:
        if for_sorting:
            if len(artist) > 1:
                last = artist[-1]
                rest = ' '.join(artist[:-1])
                artist_name = f'{last}, {rest}'
            else:
                artist_name = artist[0]
        else:
            artist_name = ' '.join(artist)
        cast_names.append(artist_name)

    return '; '.join(cast_names)


def compute_metadata_from_map(
    recording_info: 'Recording',
    mmap: dict,
) -> list[str]:
    """Process the data in recording_info, as specified in mmap."""
    args = []
    for cmd, key in mmap.items():
        rvalue = getattr(recording_info, key)
        if rvalue:
            args.extend([cmd, str(rvalue)])
    return args


def prepare_metadata_args(recording_info: 'Recording') -> list[str]:
    """Use recording_info to generate mp4tags arguments."""
    args = []
    media_type = compute_media_type(recording_info)
    args.extend(['-type', media_type])
    args.extend(['-comment', f'TabloID={recording_info.id}'])

    rescode = compute_resolution_code(recording_info)
    if rescode >= 0:
        args.extend(['-hdvideo', str(rescode)])

    cast = compute_artist(recording_info, for_sorting=False)
    if cast:
        args.extend(['-artist', cast])
    cast = compute_artist(recording_info, for_sorting=True)
    if cast:
        args.extend(['-sortartist', cast])

    if media_type == 'tvshow':
        args.extend(compute_metadata_from_map(recording_info, mmap_tv))
        args.extend(['-sortname', compute_sorted_epname(recording_info)])
    else:
        args.extend(compute_metadata_from_map(recording_info, mmap_movie))
    return args


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


def update_metadata(video_file: pathlib.Path, recording_info: 'Recording'):
    """Use mp4tags to update the metadata in video_file using recording_info."""
    args = prepare_metadata_args(recording_info)

    command = ['mp4tags']
    command.extend(args)
    command.extend([video_file])

    logger.success(f'  Updating metadata for {video_file}')
    logger.debug(command)
    # run mp4tags command...
    for line in execute(command):
        logger.debug(line, end='')


if __name__ == '__main__':
    video_folder_id = 78988  # 191181
    video_file = pathlib.Path.home().joinpath(
        'Videos',
        str(video_folder_id),
    ).with_suffix('.mp4')

    table_db = pathlib.Path.home().joinpath('Tablo.db')
    recording_data = tablo_saver.db.read_recordings(table_db)
    channel_data = tablo_saver.db.read_channels(table_db)

    rinfo = tablo_saver.db.get_recording_info(
        recording_data,
        channel_data,
        video_folder_id,
    )
    logger.debug(json.dumps(asdict(rinfo), indent=4))

    print(json.dumps(get_current_tags(video_file), indent=4))
    update_metadata(video_file, rinfo)
    print(json.dumps(get_current_tags(video_file), indent=4))

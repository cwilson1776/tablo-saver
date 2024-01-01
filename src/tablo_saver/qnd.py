"""
Module for dumping information contained within a Tablo db file.

Quick-and-dirty script to dump info from Tablo db. Issues a warning
if a recording referenced in the database does not actually have any
corresponding .ts files in the tablo mount path. Reports an error if
unable to process all of the desired data for a given recording, but
there are .ts files which correspond to it (this case would represent
an unrecoverable recording).
"""
import pathlib

import tablo_saver
from loguru import logger
from tablo_saver.db import Recording


def count_ts_files(recording_path: pathlib.Path) -> int:
    """Count the number of ts files in the specified directory."""
    sorted_file_list = [
        tsfile.name for tsfile in recording_path.iterdir() if tsfile.is_file()
    ]
    # sort the files ascending
    sorted_file_list.sort()
    ts_count = 0
    for filename in sorted_file_list:
        # only count files with .ts extension
        if (filename.endswith('.ts')):
            ts_count = ts_count + 1
    return ts_count


def make_logstr_rinfo(r_id: int, rinfo: 'Recording') -> str:
    """Generate an id string for use in log messages, given a Recording."""
    ttl = rinfo.title
    ettl = rinfo.episode_title
    logstr1 = f'{r_id} = "{ttl}"/"{ettl}"'

    evar = rinfo.entity_type
    svar = rinfo.sub_type
    logstr2 = f'{evar}/{svar}'

    evar = rinfo.episode_number
    svar = rinfo.season_number
    logstr3 = f's{evar}e{svar}'

    return f'{logstr1} : {logstr2} {logstr3}'


def make_logstr_rdict(r_id: int, rd: dict) -> str:
    """Generate an id string for use in log messages, given a dict."""
    ttl = rd.get('title')
    ettl = rd.get('episodeTitle')
    logstr1 = f'{r_id} = "{ttl}"/"{ettl}"'

    evar = rd.get('entityType')
    svar = rd.get('subType')
    logstr2 = f'{evar}/{svar}'

    evar = rd.get('episodeNum')
    svar = rd.get('seasonNum')
    logstr3 = f's{evar}e{svar}'

    return f'{logstr1} : {logstr2} {logstr3}'


def report_all(db_file: pathlib.Path, tablo_mount_path: pathlib.Path) -> None:
    """Report information about all recordings in Tablo db."""
    recording_data = tablo_saver.db.read_recordings(db_file)
    channel_data = tablo_saver.db.read_channels(db_file)
    for rd in recording_data:
        r_id = rd.get('ID')
        # make the full recording path by adding /rec , /recording_id, "/segs"
        recording_path = tablo_mount_path.joinpath('rec', str(r_id), 'segs')
        try:
            rinfo = tablo_saver.db.get_recording_info(
                recording_data,
                channel_data,
                r_id,
            )
        except Exception as exc:
            logstr = make_logstr_rdict(r_id, rd)
            if recording_path.exists():
                tsnum = count_ts_files(recording_path)
                logger.error(f'Got an exception for {logstr} ({tsnum}) {exc}')
            else:
                logger.warning(
                    f'Got an exception (but no segment dir) for {logstr} {exc}',
                )
            continue

        logstr = make_logstr_rinfo(r_id, rinfo)
        if recording_path.exists():
            tsnum = count_ts_files(recording_path)
            logger.info(f'{logstr} ({tsnum})')
            logger.info(f'    top cast = {rinfo.top_cast}')
            logger.info(f'    full cast = {rinfo.full_cast}')
            logger.info(f'    res = {rinfo.resolution_title}')
        else:
            logger.warning(f'No segment dir: {logstr}')


if __name__ == '__main__':
    # Define the mount point of the tablo hard drive, ie. the long text a49a...
    # On Ubuntu right-click hard-drive icon and properties, or use Disks tool
    tablo_mountpoint = '/media/osboxes/c6b87b95-7b93-46c8-bccb-b75c9c7f0841'
    mount_path = pathlib.Path(tablo_mountpoint)
    tablo_db = pathlib.Path.home().joinpath('Tablo.db')
    report_all(tablo_db, mount_path)

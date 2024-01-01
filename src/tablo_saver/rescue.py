"""
Module for extracting entire contents of a Tablo external drive.

Can be used to dump the database contents, rescue a single recording,
a list of recordings, or entire contents.
"""
import argparse
import importlib.metadata
import json
import pathlib
import re
import sys
from dataclasses import asdict
from typing import Optional

from loguru import logger
from tablo_saver.db import (
    Recording,
    get_recording_info,
    get_single_recording_info,
    read_channels,
    read_recordings,
)
from tablo_saver.merge import process
from tablo_saver.metadata import update_metadata


def _parse_cli(cli_args: list[str]) -> argparse.Namespace:  # noqa: WPS213
    parser = argparse.ArgumentParser(
        prog='tablo_rescue',
        description='Rescue recordings from a Tablo external drive.',
        epilog='Relies on the contents of the Tablo.db file, which is only ' +
               'updated when the user presses the reset button, so it can ' +
               'often be out of date. Also, this process only works for Gen ' +
               '3 or older Tablos; Gen 4 recordings are non-exportable.',
    )
    parser.add_argument(
        '-v',
        '--verbose',
        action='store_true',
        help='show progress',
    )
    parser.add_argument(
        '-d',
        '--debug',
        action='store_true',
        help='show debug messages',
    )
    version_str = importlib.metadata.version('tablo_saver')
    parser.add_argument(
        '-V',
        '--version',
        action='version',
        version=f'%(prog)s {version_str}',  # noqa: F821,WPS323
    )
    parser.add_argument(
        '-o',
        '--outdir',
        metavar='DIR',
        default=str(pathlib.Path.home().joinpath('Videos')),
        help='store rescued videos in DIR',
    )
    parser.add_argument(
        'tablo',
        metavar='PATH',
        help='path to tablo external drive mount-point',
    )
    parser.add_argument(
        '-I',
        '--id',
        metavar='N',
        nargs='+',
        help='only rescue (or inspect) the recording(s) with the ' +
        'specified id(s)',
    )
    parser.add_argument(
        '-f',
        '--force',
        action='store_true',
        help='force overwrite any existing output file',
    )
    parser.add_argument(
        '-D',
        '--dump',
        action='store_true',
        help='show information about recordings in the Tablo database. ' +
        'When used with -I, shows additional details about the selected ' +
        'recordings.',
    )
    parser.add_argument(
        '--dbfile',
        metavar='FILE',
        help='path to the Tablo DB (if not specified, search mountpoint)',
    )

    args = parser.parse_args(cli_args)
    logger.remove()  # remove the old handler or the both handlers will be used
    if args.debug:
        logger.add(sys.stdout, level='DEBUG')
    elif args.verbose:
        logger.add(sys.stdout, level='INFO')
    else:
        logger.add(sys.stdout, level='SUCCESS')

    return args


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


EXCLUDED_CHRS = set(r'<>:"/\|?*')  # Illegal characters in Windows filenames.
EXCLUDED_CHRS.update(chr(127))     # noqa: WPS432 (DEL is unprintable)
VALID_CHRS = frozenset(
    chr(char)
    for char in range(32, 255)  # noqa: WPS432
    if chr(char) not in EXCLUDED_CHRS
)


def sanitize_filename(fn: str) -> str:
    """Replace illegal filename characters with _."""
    return ''.join(char if char in VALID_CHRS else '_' for char in fn)


def make_filename_rinfo(r_id: int, rinfo: 'Recording') -> str:
    """Generate a filename for the specified Recording."""
    ttl = rinfo.title
    ettl = rinfo.episode_title
    ns1 = f'{r_id} {ttl}'

    evar = rinfo.entity_type
    svar = rinfo.sub_type
    ns2 = f'[{evar} {svar}]'

    ns3 = make_season_episode_str(rinfo.episode_number, rinfo.season_number)

    if evar == 'Episode':
        tmp_s = f'{ns1} - {ns3} - {ettl} - {ns2}'
    else:
        tmp_s = f'{ns1} - {ns2}'

    ns1 = re.match(r'\d+', rinfo.resolution_title)
    ns2 = 'TVRip'
    try:
        if int(ns1.group(0)) > 480:  # noqa: WPS432
            ns2 = 'HDRip'
    except ValueError:
        pass  # noqa: WPS420

    return sanitize_filename(f'{tmp_s} [{ns2}]')


def make_season_episode_str(evar: str, svar: str) -> str:  # noqa: C901
    """Create the appropriate s00e00 tag."""
    if evar:
        try:
            evar = f'e{int(evar):02d}'  # noqa: WPS237
        except ValueError:
            evar = f'e{evar}'
    if svar:
        try:
            svar = f's{int(svar):02d}'  # noqa: WPS237
        except ValueError:
            svar = f's{svar}'
    return svar + evar


def make_filename_rdict(r_id: int, rd: dict) -> str:
    """Generate a filename for the recording described by rd."""
    ttl = rd.get('title')
    ettl = rd.get('episodeTitle')
    ns1 = f'{r_id} {ttl}'

    evar = rd.get('entityType')
    svar = rd.get('subType')
    ns2 = f'[{evar} {svar}]'

    ns3 = make_season_episode_str(rd.get('episodeNum'), rd.get('seasonNum'))

    if evar == 'Episode':
        tmp_s = f'{ns1} - ${ns3} - {ettl} - {ns2}'
    else:
        tmp_s = f'{ns1} - ${ns3} - {ns2}'

    ns3 = 'TVRip'
    ns2 = ''
    ns1 = rd.get('resolution_title')
    if ns1:
        ns2 = re.match(r'\d+', ns1)
    try:
        if int(ns2) > 480:  # noqa: 432
            ns3 = 'HDRip'
    except ValueError:
        pass  # noqa: WPS420

    return sanitize_filename(f'{tmp_s} [{ns3}]')


def read_all(
    db_file: pathlib.Path,
    tablo_mount_path: pathlib.Path,
) -> tuple[int, str, int, 'Recording']:
    """Read information about all recordings in Tablo db."""
    recording_data = read_recordings(db_file)
    channel_data = read_channels(db_file)
    for rd in recording_data:
        r_id = rd.get('ID')
        # make the full recording path by adding /rec , /recording_id, "/segs"
        recording_path = tablo_mount_path.joinpath('rec', str(r_id), 'segs')
        try:
            rinfo = get_recording_info(
                recording_data,
                channel_data,
                r_id,
            )
        except Exception as exc:
            fn = make_filename_rdict(r_id, rd)
            if recording_path.exists():
                tsnum = count_ts_files(recording_path)
                logger.error(f'Got an exception for {fn} ({tsnum}) {exc}')
            else:
                logger.warning(
                    f'Got an exception (but no segment dir) for {fn} {exc}',
                )
            continue

        fn = make_filename_rinfo(r_id, rinfo)
        if recording_path.exists():
            tsnum = count_ts_files(recording_path)
            yield (r_id, fn, tsnum, rinfo)
        else:
            logger.warning(f'No segment dir: {fn}')


def report_all(db_file: pathlib.Path, tablo_mount_path: pathlib.Path) -> None:
    """Report information about all recordings in Tablo db."""
    for r_id, fn, tsnum, _ in read_all(db_file, tablo_mount_path):
        print(f'{r_id},{fn},{tsnum}')


def report_from_list(
    tablo_db: pathlib.Path,
    tablo_mount_path: pathlib.Path,
    recording_id_list: list[int],
) -> None:
    """Show detailed information about one or more individual records."""
    for count, r_id in enumerate(recording_id_list):
        logger.success(
            f'Processing recording {r_id} ' +
            f'({count+1} of {len(recording_id_list)})',
        )
        rinfo = get_single_recording_info(tablo_db, r_id)
        if rinfo:
            recording_path = tablo_mount_path.joinpath('rec', str(r_id), 'segs')
            tsnum = 0
            if recording_path.exists():
                tsnum = count_ts_files(recording_path)
            else:
                logger.warning(f'No TS files found for {r_id}')
            print(f'Recording {r_id} has {tsnum} segments')
            print(json.dumps(asdict(rinfo), indent=4))
        else:
            logger.error('Unable to retrieve information for {r_id}')


def rescue_recording(
    tablo_mount_path: pathlib.Path,
    recording_info: dict[int, 'Recording'],
    overwrite: bool,
    r_id: int,
    outdir: pathlib.Path,
) -> tuple[int, str]:
    """Rescue the recording whose Tablo database id is r_id."""
    # make the full recording path by adding /rec , /recording_id, "/segs"
    recording_path = tablo_mount_path.joinpath('rec', str(r_id), 'segs')
    try:
        rinfo = recording_info[r_id]
    except KeyError:
        logger.error(f'No recording with id {r_id} found.')
        return -1, None

    base_filename = make_filename_rinfo(r_id, rinfo)
    outfile = outdir.joinpath(base_filename).with_suffix('.mp4')

    try:
        rc = process(recording_path, outfile, overwrite)
    except Exception:
        logger.error(f'Failed to rescue recording {r_id} ({base_filename})')
        return -1, None

    if rc < 0:
        return rc, outfile

    try:
        update_metadata(outfile, rinfo)
    except Exception:
        logger.error(
            f'Failed to update metadata for recording {r_id} ({base_filename})',
        )
        return -1, None

    return 0, outfile


def rescue_from_list(
    tablo_db: pathlib.Path,
    mount_path: pathlib.Path,
    outdir: pathlib.Path,
    recording_id_list: list[int],
    overwrite: bool,
) -> bool:
    """Rescue one or more individual records."""
    rescued = {}
    skipped = {}
    for count, r_id in enumerate(recording_id_list):
        logger.success(
            f'Processing recording {r_id} ' +
            f'({count+1} of {len(recording_id_list)})',
        )
        rinfo = get_single_recording_info(tablo_db, r_id)
        if rinfo:
            rc, outfile = rescue_recording(
                mount_path,
                {r_id: rinfo},
                overwrite,
                r_id,
                outdir,
            )
            if outfile:
                if rc == 0:
                    rescued[r_id] = outfile
                elif rc == -2:
                    skipped[r_id] = outfile

    logger.success(f'Rescued {len(rescued)} recordings.')

    # Report on each specific item:
    for r_id in recording_id_list:
        if r_id in rescued.keys():
            outfile = rescued[r_id]
            print(f'Rescued:       {r_id} = {outfile}')
        elif r_id in skipped.keys():
            outfile = skipped[r_id]
            print(f'Skipped:       {r_id} = {outfile}')
        else:
            print(f'Rescue failed: {r_id}')

    return len(rescued)


def rescue_all(
    tablo_db: pathlib.Path,
    mount_path: pathlib.Path,
    outdir: pathlib.Path,
    overwrite: bool,
) -> bool:
    """Rescue all available recordings."""
    recording_info = {}
    for r_id, _, _, rinfo in read_all(tablo_db, mount_path):
        recording_info[r_id] = rinfo
        logger.info('Found {len(recording_info)} recordings')

    rescued = {}
    skipped = {}
    for count, r_id in enumerate(recording_info.keys()):
        logger.success(
            f'Processing recording {r_id} ' +
            f'({count+1} of {len(recording_info)})',
        )
        rc, outfile = rescue_recording(
            mount_path,
            recording_info,
            overwrite,
            r_id,
            outdir,
        )
        if outfile:
            if rc == 0:
                rescued[r_id] = outfile
            elif rc == -2:
                skipped[r_id] = outfile

    logger.success(f'Rescued {len(rescued)} recordings.')
    return len(rescued)


def real_main(opts: argparse.Namespace) -> bool:
    """Actual workhorse function for tablo rescue."""
    mount_path = pathlib.Path(opts.tablo)
    tablo_db = mount_path.joinpath('db').joinpath('Tablo.db')
    if opts.dbfile:
        tablo_db = pathlib.Path(opts.dbfile)

    if opts.dump:
        if opts.id:
            report_from_list(
                tablo_db,
                mount_path,
                opts.id,
            )
            return True
        report_all(tablo_db, mount_path)
        return True

    if opts.id:
        return rescue_from_list(
            tablo_db,
            mount_path,
            pathlib.Path(opts.outdir).absolute(),
            opts.id,
            overwrite=opts.force,
        )
    return rescue_all(
        tablo_db,
        mount_path,
        pathlib.Path(opts.outdir).absolute(),
        overwrite=opts.force,
    )


def main(cli_args: Optional[list[str]] = None) -> int:
    """Main entry point for rescue script."""
    if cli_args is None:
        cli_args = sys.argv[1:]

    try:
        return 0 if real_main(_parse_cli(cli_args)) else 1

    except KeyboardInterrupt:
        logger.error('Aborted manually.')
        return 1

    except Exception:
        logger.exception('Unhandled exception, exiting.')
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))

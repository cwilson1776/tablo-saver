"""
Module for extracting information from the Tablo database file.

This module implements functions necessary retrieve data from the
Tablo database file stored on an external drive. This file is only
updated when the user presses the reset button, so it can often
be out of date.
"""
import json
import pathlib
import sqlite3
from collections import namedtuple
from contextlib import closing
from dataclasses import InitVar, asdict, dataclass, field
from typing import ClassVar, Dict, Literal

from dataclasses_json import LetterCase, dataclass_json
from loguru import logger

URI_PRE: Literal['file:'] = 'file:'
URI_POST: Literal['?mode=ro'] = '?mode=ro'
ID: Literal['ID'] = 'ID'

RECORDING_FIELDS = (
    ID,
    'title',
    'json',
    'channelID',
    'origAirDate',
    'shortDescription',
    'longDescription',
    'episodeTitle',
    'episodeNum',
    'seasonNum',
    'topCast',
    'fullCast',
    'entityType',
    'subType',
)
CHANNEL_FIELDS = (
    ID,
    'callSign',
    'channelNumberMajor',
    'channelNumberMinor',
    'resolutionTitle',
)


def make_uri(db_file: pathlib.Path) -> str:
    """Create a sqlite URI from a db filename."""
    return f'{URI_PRE}{db_file}{URI_POST}'


def namedtuple_factory(cursor, row):
    """A row factory for sqlite3."""
    fields = [column[0] for column in cursor.description]
    cls_type = namedtuple('Row', fields)
    return cls_type._make(row)  # noqa: WPS437


def dict_factory(cursor, row):
    """A row factory for sqlite3."""
    fields = [column[0] for column in cursor.description]
    return dict(zip(fields, row))


def read_recordings(db_file: pathlib.Path) -> list[dict]:
    """Reads the Tablo DB and returns a list of records from Recording."""
    query = (
        'SELECT ' +  # noqa: S608
        ', '.join(RECORDING_FIELDS) +
        ' FROM Recording' +
        ' WHERE ID > 0' +
        ' AND LENGTH(DateDeleted) < 1' +
        ' ORDER BY title'
    )
    with closing(sqlite3.connect(database=make_uri(db_file), uri=True)) as conn:
        with conn:  # as transaction
            conn.row_factory = dict_factory
            with closing(conn.cursor()) as cur:
                all_rows = cur.execute(query).fetchall()

    return all_rows


def read_one_recording(db_file: pathlib.Path, r_id: int) -> dict:
    """Reads the Tablo DB and returns a one record from Recording."""
    query = (
        'SELECT ' +  # noqa: S608
        ', '.join(RECORDING_FIELDS) +
        ' FROM Recording' +
        ' WHERE ID = ' +
        str(r_id) +
        ' AND LENGTH(DateDeleted) < 1' +
        ' ORDER BY title'
    )
    with closing(sqlite3.connect(database=make_uri(db_file), uri=True)) as conn:
        with conn:  # as transaction
            conn.row_factory = dict_factory
            with closing(conn.cursor()) as cur:
                row = cur.execute(query).fetchone()

    return row


def read_channels(db_file: pathlib.Path) -> list[dict]:
    """Reads the Tablo DB and returns a list of records from Channel."""
    query = (
        'SELECT ' +  # noqa: S608
        ', '.join(CHANNEL_FIELDS) +
        ' FROM Channel' +
        ' ORDER BY ID'
    )
    with closing(sqlite3.connect(database=make_uri(db_file), uri=True)) as conn:
        with conn:  # as transaction
            conn.row_factory = dict_factory
            with closing(conn.cursor()) as cur:
                all_rows = cur.execute(query).fetchall()

    return all_rows


def read_one_channel(db_file: pathlib.Path, chan_id: int) -> dict:
    """Reads the Tablo DB and returns a list of records from Channel."""
    query = (
        'SELECT ' +  # noqa: S608
        ', '.join(CHANNEL_FIELDS) +
        ' FROM Channel ' +
        ' WHERE ID = ' +
        str(chan_id) +
        ' ORDER BY ID'
    )
    with closing(sqlite3.connect(database=make_uri(db_file), uri=True)) as conn:
        with conn:  # as transaction
            conn.row_factory = dict_factory
            with closing(conn.cursor()) as cur:
                row = cur.execute(query).fetchone()

    return row


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass(kw_only=True)
class Recording(object):
    """Class for keeping track of metadata about a recording."""

    id: int
    title: str
    channel_id: int
    orig_air_date: str = field(default='')
    short_description: str = field(default='')
    long_description: str = field(default='')
    episode_title: str = field(default='')
    episode_number: int = field(default=0)
    season_number: int = field(default=0)
    top_cast: str = field(default='')
    full_cast: str = field(default='')
    entity_type: str = field(default='')
    sub_type: str = field(default='')
    call_sign: str = field(default='')
    channel_number_major: int = field(default=None)
    channel_number_minor: int = field(default=None)
    resolution_title: str = field(default='')
    _json_string: InitVar[str | None] = None
    _uninit_json_data: ClassVar[Dict] = {}
    json_data: Dict = field(
        default_factory=lambda: Recording._uninit_json_data,  # noqa: WPS437
    )

    def __post_init__(self, _json_string) -> None:
        """Initialize json_data by parsing _json_string."""
        if self.json_data is self._uninit_json_data:
            if _json_string is not None:
                self.json_data = json.loads(_json_string)  # noqa: WPS601

    recording_keymap = {
        ID: 'id',
        'title': 'title',
        'origAirDate': 'orig_air_date',
        'shortDescription': 'short_description',
        'longDescription': 'long_description',
        'topCast': 'top_cast',
        'fullCast': 'full_cast',
        'entityType': 'entity_type',
        'subType': 'sub_type',
        'episodeTitle': 'episode_title',
        'episodeNum': 'episode_number',
        'seasonNum': 'season_number',
        'channelID': 'channel_id',
        'json': '_json_string',
    }
    channel_keymap = {
        'callSign': 'call_sign',
        'channelNumberMajor': 'channel_number_major',
        'channelNumberMinor': 'channel_number_minor',
        'resolutionTitle': 'resolution_title',
    }
    json_keymap = {
        'description': 'long_description',
        'episodeNumber': 'episode_number',
        'seasonNumber': 'season_number',
        'originalAirDate': 'orig_air_date',
    }

    @classmethod
    def fromdict(cls, recording_dict):
        """Construct and initialize a Recording object from a db row."""
        kwargs = {}
        for oldk, newk in cls.recording_keymap.items():
            db_value = recording_dict.get(oldk)
            if db_value:
                kwargs[newk] = db_value
        return cls(**kwargs)

    def update_item_from_channel(
        self,
        channel_name: str,
        channel_data: dict,
        overwrite: bool = True,
    ):
        """Update specific member using information from Channel table."""
        ch_value = channel_data.get(channel_name)
        member_name = self.channel_keymap.get(channel_name)
        if ch_value and (overwrite or not self.__getattribute__(member_name)):
            self.__setattr__(member_name, ch_value)

    def update_channel_info(self, channels: list[dict], overwrite: bool = True):
        """Update channel information using entry in Channel table."""
        channel_data = [
            chan for chan in channels if chan.get(ID) == self.channel_id
        ]
        if channel_data:
            self.update_item_from_channel(
                'callSign',
                channel_data[0],
                overwrite=overwrite,
            )
            self.update_item_from_channel(
                'channelNumberMajor',
                channel_data[0],
                overwrite=overwrite,
            )
            self.update_item_from_channel(
                'channelNumberMinor',
                channel_data[0],
                overwrite=overwrite,
            )
            self.update_item_from_channel(
                'resolutionTitle',
                channel_data[0],
                overwrite=overwrite,
            )

    def update_item_from_json(self, json_name: str, overwrite: bool = True):
        """Update a specific member using information from self.json."""
        json_value = self.json_data.get(json_name)
        member_name = self.json_keymap.get(json_name)
        if json_value and (overwrite or not self.__getattribute__(member_name)):
            self.__setattr__(member_name, json_value)

    def update_from_json(self, overwrite: bool = True):
        """Update members from self.json."""
        self.update_item_from_json('originalAirDate', overwrite=overwrite)
        self.update_item_from_json('description', overwrite=overwrite)
        self.update_item_from_json('episodeNumber', overwrite=overwrite)
        self.update_item_from_json('seasonNumber', overwrite=overwrite)


def list_tables(db_file: pathlib.Path) -> list[str]:
    """Reads the Tablo DB and returns a list of tables."""
    query = "SELECT name FROM sqlite_master WHERE type='table';"
    with closing(sqlite3.connect(database=make_uri(db_file), uri=True)) as conn:
        with conn:  # as transaction
            conn.text_factory = str
            with closing(conn.cursor()) as cur:
                tables = cur.execute(query).fetchall()
                table_names = sorted(list(zip(*tables))[0])

    return table_names


def dump_schema(db_file: pathlib.Path, table_name: str) -> list[str]:
    """Reads the Tablo DB and returns the schema for a table."""
    query = f"PRAGMA table_info('{table_name}')"
    with closing(sqlite3.connect(database=make_uri(db_file), uri=True)) as conn:
        with conn:  # as transaction
            conn.text_factory = str
            with closing(conn.cursor()) as cur:
                columns = cur.execute(query).fetchall()
                column_names = list(zip(*columns))[1]

    return column_names


def get_recording_info(
    recording_data: list[dict],
    channel_data: list[dict],
    recording_id: int,
) -> 'Recording':
    """Retrieve metadata for a recording from the Tablo db."""
    selected_data = [
        rec for rec in recording_data if rec.get(ID) == recording_id
    ]
    if selected_data:
        if len(selected_data) == 1:
            recording_result = Recording.fromdict({**selected_data[0]})
            recording_result.update_channel_info(channel_data, overwrite=False)
            recording_result.update_from_json(overwrite=False)
        else:
            logger.error(f'Multiple entries found for recording {recording_id}')
            for duplicate in selected_data:
                logger.debug(json.dumps({**duplicate}, indent=4))
            return None
    else:
        logger.error(f'No data found for recording {recording_id}')
        return None

    logger.debug(json.dumps(asdict(recording_result)))
    return recording_result


def get_single_recording_info(db_file: pathlib.Path, r_id: int) -> 'Recording':
    """Retrieve metadata for a recording from the Tablo db."""
    recording_data = read_one_recording(db_file, r_id)
    if not recording_data:
        logger.error(f'No data found for recording {r_id}')
        return None

    recording_result = Recording.fromdict({**recording_data})
    channel_data = read_one_channel(db_file, recording_result.channel_id)
    if not channel_data:
        logger.error(
            'No channel information found for ' +
            f'channel_id={recording_result.channel_id}',
        )
        return None

    recording_result.update_channel_info([channel_data], overwrite=False)
    recording_result.update_from_json(overwrite=False)
    logger.debug(json.dumps(asdict(recording_result)))
    return recording_result


if __name__ == '__main__':
    TEST_RECORDING_ID = 2494457
    tablo_db = pathlib.Path.home().joinpath('Tablo.db')
    recording_data = read_recordings(tablo_db)
    channel_data = read_channels(tablo_db)
    r_info = get_recording_info(recording_data, channel_data, TEST_RECORDING_ID)
    str_json = r_info.to_json()
    r_info2 = Recording.from_json(str_json)

    print(json.dumps(asdict(r_info), indent=4))
    print(json.dumps(asdict(r_info2), indent=4))

    r_info3 = get_single_recording_info(tablo_db, 2494457)

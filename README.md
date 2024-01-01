# tablo-saver

Save recordings from tablo external drive. Note that this works only
with Gen 3 Tablos and older. With Gen 4, the ability to extract
recordings was blocked (I suspect by demand of Tablo's content
partners when they introduced internet-based streaming channels).


## Usage

```
usage: tablo_rescue [-h] [-v] [-d] [-V] [-o DIR] [-I N [N ...]] [-f]
                    [-D] [--dbfile FILE]
                    PATH

Rescue recordings from a Tablo external drive.

positional arguments:
  PATH                  Path to tablo external drive mount-point

options:
  -h, --help            show this help message and exit
  -v, --verbose         show progress
  -d, --debug           show debug messages
  -V, --version         show program's version number and exit
  -o DIR, --outdir DIR  store rescued videos in DIR
  -I N [N ...], --id N [N ...]
                        only rescue (or inspect) the recording(s)
                        with the specified id(s)
  -f, --force           force overwrite any existing output file
  -D, --dump            show information about recordings in the
                        Tablo database. When used with -I, shows
                        additional details about the selected
                        recordings.
  --dbfile FILE         path to the Tablo DB (if not specified,
                        search mountpoint)

Relies on the contents of the Tablo.db file, which is only updated
when the user presses the reset button, so it can often be out of
date. Also, this process only works for Gen 3 or older Tablos; Gen 4
recordings are non-exportable.
```

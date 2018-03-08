# apollo-cli

A tool to interact with apollo.rip and provide enhanced functionality via a command line interface.

Currently only automatic transcoding and uploading similar to _xanaxbetter_ is implemented. Though the scope of this project is not limited to this and additional features might be implemented in the future.

apollo-cli should in theory work on most platforms but Linux is the only tested and officially supported platform.

## Installation

Just clone this repository and install the required dependencies.

### Dependencies

apollo-cli requires a recent version of Python 3. Any version >=3.5 should work but it is only tested with 3.6.

The required python libraries are listed in `requirements.txt` and can be installed via `pip`:

```
$ pip install -r requirements.txt
```

You also need to have the following tools installed on you system and available in your `PATH`:

* flac (https://xiph.org/flac/)
* sox (http://sox.sourceforge.net/)
* lame (http://lame.sourceforge.net/)
* mktorrent (https://github.com/Rudde/mktorrent) version 1.1 or newer

These tools should be available in the package repositories of all major Linux Distributions so installation should be trivial.

## Configuration

Create a file called `apollobetter.conf` in the same directory as `apollobetter.py` with the following content:

```
[DEFAULT]
torrent_cache=cache.json

[apollo]
username=user
password=pass
```

Replace `user` and `pass` with your apollo.rip username and password an you are good to go.

## Usage

The most basic usage is:

```
python apollobetter.py --search-dir /media/data/downloads -o /media/data/downloads --torrent-dir /media/data/watch
```

With this command apollo-cli will search for FLAC releases in `/media/data/downloads`, place transcoded releases there as well and place the `*.torrent` files in `/media/data/watch`.

If you have FLAC releases in multiple different directories you can just specify `--search-dir` multiple times and apollo-cli will search in all of them.

By default apollo-cli will transcode to all formats that are missing for the release on apollo.rip. If you want to transcode only to specific formats you can do so by adding one or more of the flags `-v2`, `-v0`, `-320`.

To limit the number of torrents it will generate and upload you can use the `--limit` option.

A very useful option if you want to transcode many releases at once is `--continue-on-error`. With this option apollo-cli will just continue with the next release if it encounters a non-critical error.

The following command will print a help text with a list of all options:

```
python apollobetter.py -h
```

## Contributing

You can report bugs and feature requests in the github issue tracker of the project.

Feel free to open a pull request if you added functionality or fixed a bug.

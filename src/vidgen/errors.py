"""Error types raised by vidgen."""


class VidgenError(Exception):
    """An error the user can cause and fix (bad config, missing file, unknown name, ...).

    The CLI prints these as ``error: <message>`` without a traceback.
    """

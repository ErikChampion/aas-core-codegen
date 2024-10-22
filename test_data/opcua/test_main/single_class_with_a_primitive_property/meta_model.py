"""
This is the most basic unit test to kick off the development of the OPC UA node set generator.
"""


class Something(DBC):
    text: str
    """This is some text."""

    def __init__(self, text: str) -> None:
        self.text = text

__version__ = "dummy"
__xml_namespace__ = "https://dummy.com"

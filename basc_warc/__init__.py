# -*- coding: utf-8 -*-
# BASC-WARC library
#
# Written in 2015 by Daniel Oaks <daniel@danieloaks.net>
#
# To the extent possible under law, the author(s) have dedicated all copyright
# and related and neighboring rights to this software to the public domain
# worldwide. This software is distributed without any warranty.
#
# You should have received a copy of the CC0 Public Domain Dedication along
# with this software. If not, see
# <http://creativecommons.org/publicdomain/zero/1.0/>.
"""Create and manage WARC files."""
import sys
import threading

import basc_warc.utils

__version__ = '0.0.1'

WARC_VERSION = b'WARC/1.0'
WARC_SOFTWARE = (b'BASC-WARC/' + __version__.encode('utf8') +
                 b' Python/' + sys.version.encode('utf8'))
CRLF = b'\r\n'

warc_sort_keyfn = basc_warc.utils.sort_manual_keys(
    'WARC-Type', 'WARC-Record-ID', 'WARC-Date',
    'Content-Length', 'Content-Type', 'WARC-Concurrent-To',
    'WARC-Block-Digest', 'WARC-Payload-Digest',
    'WARC-IP-Address', 'WARC-Refers-To',
    'WARC-Target-URI', 'WARC-Truncated',
    'WARC-Warcinfo-ID', 'WARC-Filename',
    'WARC-Profile', 'WARC-Identified-Payload-Type',
    'WARC-Segment-Origin-ID', 'WARC-Segment-Number',
    'WARC-Segment-Total-Length')


class WarcFile(object):
    """A WARC (Web ARChive) file."""

    def __init__(self, records=[]):
        self.records = records
        self.records_lock = threading.Lock()

    # output
    def bytes(self, compress_records=False):
        """Return bytes to write.

        Args:
            compress_records (bool): Whether to apply gzip compression to records.

        Returns:
            Bytes that represent this WARC file.
        """
        warc = bytes()

        with self.records_lock:
            for record in self.records:
                if compress_records:
                    print('Cannot compress records yet.')
                else:
                    warc += record.bytes()

        return warc

    # adding records
    def add_record(self, record):
        """Add the given Record to our records.

        Args:
            record: :class:`basc_warc.Record` to add to this WARC file.

        Returns:
            The index of the added record.
        """
        record_indexes = self.add_records(record)
        return record_indexes[0]

    def add_records(self, *records):
        """Add the given Records to our records.

        Args:
            record (list of :class:`basc_warc.Record`): Records to add to this WARC file.

        Returns:
            Indexes of the added records.
        """
        record_indexes = []

        with self.records_lock:
            for record in records:
                record_index = len(self.records)
                record_indexes.append(record_index)

                self.records.append(record)

        return record_indexes

    def add_warcinfo_record(self, fields={}, operator=None, software=None,
                            robots=None, hostname=None, ip=None,
                            http_header_user_agent=None, http_header_from=None):
        """Add a warcinfo record to this file.

        Args:
            fields (dict): Fields for this record.
            operator (string): Contact information for the operator who created this resource.
                A name or a name and email address is recommended.
            software (string): Software and software version used to create this WARC resource
                (defaults to BASC-Warc's version informaton).
            robots (string): The robots policy followed by the harvester creating this WARC
                resource. The string ``'classic'`` indicates the 1994 web robots exclusion
                standard rules are being obeyed.
            hostname (string): The hostname of the machine that created this WARC resource,
                such as "crawling17.archive.org".
            ip (string): The IP address of the machine that created this WARC resource, such as
                "123.2.3.4".
            http_header_user_agent (string): The HTTP 'user-agent' header usually sent by the
                harvester along with each request. If 'request' records are used to save
                verbatim requests, this information is redundant.
            http_header_from (string): The HTTP 'From' header usually sent by the harvester
                along with each request (redundant when 'request' records are used, as above).

        Returns:
            Index of the new added record.
        """
        # assemble fields
        if operator:
            fields['operator'] = operator
        if software:
            fields['software'] = software
        if robots:
            fields['robots'] = robots
        if hostname:
            fields['hostname'] = hostname
        if ip:
            fields['ip'] = ip
        if http_header_user_agent:
            fields['http-header-user-agent'] = http_header_user_agent
        if http_header_from:
            fields['http-header-from'] = http_header_from

        # create record
        header = RecordHeader({})
        block = WarcinfoBlock(fields)
        new_record = Record('warcinfo', header=header, block=block)

        record_index = self.add_record(new_record)
        return record_index


class Record(object):
    """A record in a WARC file."""

    def __init__(self, record_type, header=None, block=None):
        self.record_type = record_type
        self.header = header
        self.block = block

    def bytes(self):
        """Return bytes to write."""
        self.header.set_field('Content-Length', self.block.length())
        return self.header.bytes() + CRLF + self.block.bytes() + CRLF + CRLF


class RecordHeader(object):
    """A header for a WARC record."""

    def __init__(self, fields={}):
        self.fields = fields

    def set_field(self, name, value):
        """Set field to the given value."""
        self.field[name] = value

    def bytes(self):
        """Return bytes to write."""
        field_bytes = bytes()

        for key, value in sorted(self.fields.items(), key=warc_sort_keyfn):
            if isinstance(key, str):
                key = key.encode('utf8')
            if isinstance(value, str):
                value = value.encode('utf8')

            field_bytes += key + b': ' + value

        return WARC_VERSION + CRLF + field_bytes + CRLF


class RecordBlock(object):
    """Block for an arbitrary record."""

    def __init__(self, content=None):
        if content is None:
            self.content = bytes()
        else:
            self.content = bytes(content)

    def bytes(self):
        """Return bytes to write."""
        return self.content

    def length(self):
        """Return length in bytes."""
        return len(self.content)


class WarcinfoBlock(object):
    """Block for a warcinfo record."""

    def __init__(self, fields={}):
        self.fields = fields
        self._cache = None

    def set_field(self, name, value):
        """Set field to given value."""
        self.fields[name] = value
        self._cache = None

    def bytes(self):
        """Return bytes to write."""
        if self._cache is None:
            # assemble block items
            info_fields = []

            for key, value in self.fields.items():
                if isinstance(key, str):
                    key = key.encode('utf8')
                if isinstance(value, str):
                    value = value.encode('utf8')

                info_fields.append(key + b': ' + value)

            # assemble into final block
            info = CRLF.join(info_fields)

            self._cache = info

        return self._cache

    def length(self):
        """Return length in bytes."""
        return len(self.bytes())

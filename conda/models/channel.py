# -*- coding: utf-8 -*-
from __future__ import absolute_import, division, print_function, unicode_literals

from collections import OrderedDict
from itertools import chain
from logging import getLogger
from os.path import exists, join

from ..base.constants import PLATFORM_DIRECTORIES, RECOGNIZED_URL_SCHEMES
from ..base.context import context
from ..common.url import path_to_url, urlparse, urlunparse, is_url

log = getLogger(__name__)


def get_conda_build_local_url():
    try:
        from conda_build.config import croot
    except ImportError:
        return None
    except Exception:
        import traceback
        log.debug(traceback.format_exc())
        return None
    return [path_to_url(croot)] if exists(croot) else None


def has_scheme(value):
    return bool(urlparse(value).scheme in RECOGNIZED_URL_SCHEMES)


def join_url(*args):
    return '/'.join(args) + '/'


class Channel(object):
    _cache_ = dict()
    _local_url = get_conda_build_local_url()
    _channel_alias_netloc = urlparse(context.channel_alias).netloc

    def __new__(cls, value):
        if isinstance(value, Channel):
            return value
        elif value in Channel._cache_:
            return Channel._cache_[value]
        elif value in _SPECIAL_CHANNELS:
            self = object.__new__(_SPECIAL_CHANNELS[value])
        elif value.endswith('.tar.bz2'):
            self = object.__new__(UrlChannel)
        elif has_scheme(value):
            self = object.__new__(UrlChannel)
        else:
            self = object.__new__(NamedChannel)
        Channel._cache_[value] = self
        return self

    @staticmethod
    def _reset_state():
        Channel._cache_ = dict()
        Channel._local_url = get_conda_build_local_url()
        Channel._channel_alias_netloc = urlparse(context.channel_alias).netloc

    @property
    def base_url(self):
        return urlunparse((self._scheme, self._netloc, self._path, None, None, None))

    def __eq__(self, other):
        return self._netloc == other._netloc and self._path == other._path

    @property
    def canonical_name(self):
        if any(self == Channel(c) for c in context.default_channels):
            return 'defaults'
        elif self._local_url and any(self == Channel(c) for c in self._local_url):
            return 'local'
        elif self._netloc == Channel(context.channel_alias)._netloc:
            # TODO: strip token
            return self._path.lstrip('/')
        else:
            return self.base_url

    @property
    def urls(self):
        # TODO: figure out how to add token
        if self._platform is None:
            return [join_url(self.base_url, context.subdir), join_url(self.base_url, 'noarch')]
        else:
            return [join_url(self.base_url, self._platform)]

    @property
    def url_channel_wtf(self):
        # return channel, schannel
        # url_channel in >> https://repo.continuum.io/pkgs/free/osx-64/requests-2.0-py27_0.tar.bz2
        # url_channel out >> https://repo.continuum.io/pkgs/free defaults
        return self.base_url, self.canonical_name


def split_platform(value):
    parts = value.rstrip('/').rsplit('/', 1)
    if len(parts) == 2 and parts[1] in PLATFORM_DIRECTORIES:
        return parts[0], parts[1]
    else:
        return value, None


class UrlChannel(Channel):

    def __init__(self, url):
        if url.endswith('.tar.bz2'):
            url = url.rsplit('/', 1)[0]
        if not has_scheme(url):
            url = path_to_url(url)
        self._raw_value = url
        parsed = urlparse(url)
        self._scheme = parsed.scheme
        self._netloc = parsed.netloc
        self._path, self._platform = split_platform(parsed.path)


class NamedChannel(Channel):

    def __init__(self, name):
        self._raw_value = name
        parsed = urlparse(context.channel_alias)
        self._scheme = parsed.scheme
        self._netloc = parsed.netloc
        self._path = join(parsed.path, name)
        self._platform = None


class DefaultChannel(NamedChannel):

    @property
    def canonical_name(self):
        return "defaults"

    @property
    def urls(self):
        return list(chain.from_iterable(Channel(c).urls for c in context.default_channels))


class LocalChannel(UrlChannel):

    def __init__(self, _):
        super(LocalChannel, self).__init__(get_conda_build_local_url())

    @property
    def canonical_name(self):
        return "local"


class NoneChannel(NamedChannel):

    def __init__(self, value):
        self._raw_value = value
        self._scheme = self._netloc = self._path = self._platform = None

    @property
    def canonical_name(self):
        return "<unknown>"

    @property
    def urls(self):
        return tuple()


def prioritize_channels(channels):
    # ('https://conda.anaconda.org/conda-forge/osx-64/', ('conda-forge', 1))
    result = OrderedDict()
    for q, chn in enumerate(channels):
        channel = Channel(chn)
        for url in channel.urls:
            result[url] = channel.canonical_name, q
    return result


def offline_keep(url):
    return not context.offline or not is_url(url) or url.startswith('file:/')


_SPECIAL_CHANNELS = {
    'defaults': DefaultChannel,
    'local': LocalChannel,
    None: NoneChannel,
}

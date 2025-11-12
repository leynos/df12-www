"""Common literal values used across df12_pages.

These constants keep filenames and metadata keys centralized so templates,
generators, and tests can import the same values without drifting. Intended for
internal use within the df12_pages package.

Examples
--------
>>> from df12_pages import _constants
>>> _constants.PAGE_META_TEMPLATE.format(key="netsuke")
'.df12-pages-netsuke-meta.json'
>>> meta_path = _constants.PAGE_META_TEMPLATE.format(key="femtologging")
>>> meta_path.endswith('-meta.json')
True
"""

PAGE_META_TEMPLATE = ".df12-pages-{key}-meta.json"

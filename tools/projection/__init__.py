"""Hybrid Equal Earth projection (DEC-035, WU P00d).

``hybrid``      forward / inverse / canvas helpers and the CLI (selftest | info | preview)
``naturalearth`` pinned Natural Earth 1:50m land download + a minimal shapefile reader
``places``      key-place distortion table
``render``      preview images, heat maps and the contact sheet
``reports``     top-edge (Q-014) and seam-sensitivity reports

The Equal Earth maths is never re-implemented here: it is imported from the
skill's ``ee_project.py`` (``.claude/skills/hoi4-map-modding/scripts``).
"""

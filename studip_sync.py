#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from studip_sync.studip_sync import StudipSync

with StudipSync() as s:
    exit(s.sync())

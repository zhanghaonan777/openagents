# -*- coding: utf-8 -*-
"""Tests for the structured-logging kv() helper."""
from app.logfmt import kv


def test_kv_renders_pairs_and_skips_none():
    assert kv(event="01J", ws="abc", agent=None, n=3) == "event=01J ws=abc n=3"


def test_kv_lists_and_empty_and_quoting():
    assert kv(targets=["bob", "carol"]) == "targets=bob,carol"
    assert kv(targets=[]) == "targets=-"
    assert kv(msg="hello world") == 'msg="hello world"'
    assert kv(s="") == 's=""'


def test_kv_empty():
    assert kv() == ""

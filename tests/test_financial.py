import pytest
import pandas as pd
import numpy as np

from src.financial import expand_array, add_to_first_n


class TestExpandArray:
    def test_basic_expansion(self):
        items = [{"year": 0, "value": "a"}, {"year": 3, "value": "b"}]
        result = expand_array(items, "year", 5)
        assert len(result) == 5
        assert result[0]["value"] == "a"
        assert result[1] is None
        assert result[2] is None
        assert result[3]["value"] == "b"
        assert result[4] is None

    def test_empty_input(self):
        result = expand_array([], "year", 3)
        assert result == [None, None, None]

    def test_out_of_range_ignored(self):
        items = [{"year": 10, "value": "x"}]
        result = expand_array(items, "year", 5)
        assert all(v is None for v in result)


class TestAddToFirstN:
    def test_extends_array(self):
        ar = [1.0, 2.0]
        result = add_to_first_n(ar, 10.0, 4)
        assert len(result) == 4
        assert result[0] == 11.0
        assert result[1] == 12.0
        assert result[2] == 10.0
        assert result[3] == 10.0

    def test_no_extension_needed(self):
        ar = [1.0, 2.0, 3.0, 4.0]
        result = add_to_first_n(ar, 5.0, 2)
        assert result[0] == 6.0
        assert result[1] == 7.0
        assert result[2] == 3.0
        assert result[3] == 4.0

# finds

`finds` is a fault injection and detection suite based on `pytest`.

## Quick Start

```
# install deps
pip install -r requirements.txt

# run tests
python -m pytest
```

## Structure

```
lab/                    # code stubs
  contentions.py        # thread, i/o, cpu contention
  deadlocks.py          # tbd
  hazards.py            # tbd
tests/                  # test suite
  conftest.py           # reusables (common imports, fixtures, etc,) - tbd
  test_contentions.py
  test_deadlocks.py
  test_hazards.py
tools/                  # placeholder for some tools & utils
```

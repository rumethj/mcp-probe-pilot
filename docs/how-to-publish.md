# How-to Publish to PyPi Manually

## Pre-requisites

1. Ensure that the API Token is set.
2. Install dependencies
```shell
pip install build twine
```

## 0. Go to Package directory

```shell
cd mcp-probe-pilot
```

## 1. Build the Package

This creates dist/mcp_probe_pilot-0.1.0.tar.gz and dist/mcp_probe_pilot-0.1.0-py3-none-any.whl.
```shell
python -m build
```


## 2. Upload to PyPi

```shell
twine upload dist/*
```


It will prompt you for:
```shell
Username: __token__
Password: <your PyPI API token>
```
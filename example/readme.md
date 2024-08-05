# Pytest-mh example code

This directory contains an example show case of the pytest-mh plugin. This
example shows a basic framework and tests for `sudo`, since this is the tool
that every power user is familiar with and at the same time it is possible to
demonstrate many pytest-mh features, including advanced topology controllers and
topology parametrization.

> [!NOTE]
>
> The example test framework is far from being perfect. In order to keep it
> simple, it lacks many features that would be needed to test sudo completely.
> Even the API that was implemented is intentionally limited and does not
> support every single format of the sudo rule.
>
> Some parts of the framework could have been implemented differently, even in a
> better way. However, optimal implementation was sacrificed on multiple places
> in order to demonstrate more pytest-mh features.

## Running tests

1. Start containers

```
sudo docker-compose  -f containers/docker-compose.yml up --detach
```

2. Install test requirements

```
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install pytest-mh in editable mode from sources
pip3 install -e ..

# Install test requirements
pip3 install -r ./requirements.txt
```

3. Run the tests

```
pytest --mh-config=./mhc.yaml
```
